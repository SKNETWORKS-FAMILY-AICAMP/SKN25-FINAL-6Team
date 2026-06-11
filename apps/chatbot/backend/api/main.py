from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from common.observability.langsmith import configure_langsmith
from common.db.connection import db_connection

configure_langsmith("chatbot")

from chatbot.service.account_service import get_server_regions, login_with_credentials
from chatbot.service.chatbot_service import run_chatbot
from chatbot.service.multiturn_service import build_session_context


app = FastAPI(title="GameOps Chatbot API")

cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CHATBOT_CORS_ORIGINS",
        "null,http://127.0.0.1:8000,http://localhost,http://127.0.0.1",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

ChatCategory = Literal["payment", "bug", "faq", "voc"]


class ChatRequest(BaseModel):
    ticket_id: int | None = None
    user_message: str = Field(min_length=1)
    category: ChatCategory
    account_id: int | None = None
    user_id: int = 1
    session_id: str | int | None = None
    source_type: str = "chatbot"
    ui_category: str | None = None
    sub_category: str | None = None
    routing_target: str | None = None
    should_use_rag: bool | None = None
    fallback_routing_target: str | None = None
    previous_messages: list[dict[str, str]] | None = None
    conversation_summary: str | None = None


class ChatResponse(BaseModel):
    answer: str
    ticket_id: int
    session_id: str
    draft_id: int | None = None
    category: str | None = None
    ui_category: str | None = None
    sub_category: str | None = None
    routing_target: str | None = None
    review_required: bool | None = None
    safety_passed: bool | None = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    server_region: str = Field(min_length=1)


class LoginResponse(BaseModel):
    login_success: bool
    user_id: int | None = None
    account_id: int | None = None
    game_id: str = ""
    email: str = ""
    server_region: str = ""
    nickname: str | None = None
    message: str = ""


class InquiryHistoryItem(BaseModel):
    ticket_id: int
    title: str | None = None
    raw_query: str | None = None
    status: str | None = None
    source_type: str | None = None
    inquiry_created_at: Any | None = None
    final_text: str | None = None


def _extract_ai_response(raw_query: str | None) -> str | None:
    if not raw_query:
        return None
    marker = "\nAI: "
    idx = raw_query.find(marker)
    if idx == -1:
        return None
    return raw_query[idx + len(marker):]


def _new_numeric_id() -> int:
    return 100_000_000 + secrets.randbelow(800_000_000)


def _new_ticket_id() -> int:
    for _ in range(8):
        ticket_id = _new_numeric_id()
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM qa_ticket WHERE ticket_id = %s", (ticket_id,))
                    if cur.fetchone() is None:
                        return ticket_id
        except Exception:
            return ticket_id
    return _new_numeric_id()


def _next_session_turn_id(previous_session_id: str | int | None) -> str:
    if not previous_session_id:
        return f"{_new_numeric_id()}-1"

    session_id = str(previous_session_id).strip()
    if not session_id:
        return f"{_new_numeric_id()}-1"

    base, separator, turn = session_id.rpartition("-")
    if separator and base and turn.isdigit():
        return f"{base}-{int(turn) + 1}"
    return f"{session_id}-1"


@app.get("/health")
def health() -> dict[str, str]:
    # 배포/헬스체크용: API 프로세스가 살아 있는지만 빠르게 확인한다.
    return {"status": "ok"}


@app.get("/server-regions")
def server_regions() -> dict[str, list[str]]:
    # 로그인 화면에서 선택할 수 있는 서버 목록을 DB에서 읽어온다.
    return {"items": get_server_regions()}


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    # 1단계: 이메일/비밀번호/서버로 게임 계정을 확인하고 user_id/account_id를 반환한다.
    result = login_with_credentials(request.email, request.password, request.server_region)
    return LoginResponse(**result)


@app.get("/tickets", response_model=list[InquiryHistoryItem])
def list_tickets(
    user_id: int = Query(..., ge=1),
    account_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[InquiryHistoryItem]:
    # 1단계: 로그인 사용자의 최근 문의와 최신 final_response를 함께 조회한다.
    params: list[Any] = [user_id]
    account_filter = ""
    if account_id is not None:
        account_filter = "AND t.account_id = %s"
        params.append(account_id)
    params.append(limit)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.raw_query,
                    t.status,
                    t.source_type,
                    t.inquiry_created_at
                FROM qa_ticket t
                WHERE t.user_id = %s
                AND COALESCE(t.source_type, 'chatbot') <> 'eval'
                {account_filter}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()

    return [
        InquiryHistoryItem(
            ticket_id=row[0],
            title=row[1],
            raw_query=row[2],
            status=row[3],
            source_type=row[4],
            inquiry_created_at=row[5],
            final_text=_extract_ai_response(row[2]),
        )
        for row in rows
    ]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    ticket_id = _new_ticket_id()
    session_id = _next_session_turn_id(request.session_id)

    # 1단계: 요청에 이전 대화가 없으면 DB에서 최근 멀티턴 context를 구성한다.
    previous_messages = request.previous_messages
    conversation_summary = request.conversation_summary
    if previous_messages is None:
        context = build_session_context(
            session_id=session_id,
            user_id=request.user_id,
            account_id=request.account_id,
            current_ticket_id=ticket_id,
            recent_turns=3,
        )
        previous_messages = context.previous_messages
        conversation_summary = conversation_summary or context.conversation_summary

    # 2단계: chatbot_service가 LangGraph workflow를 실행하고 최종 답변/state를 반환한다.
    output: dict[str, Any] = run_chatbot(
        ticket_id=ticket_id,
        user_message=request.user_message,
        category=request.category,
        account_id=request.account_id,
        user_id=request.user_id,
        session_id=session_id,
        source_type=request.source_type,
        ui_category=request.ui_category,
        sub_category=request.sub_category,
        routing_target=request.routing_target,
        should_use_rag=request.should_use_rag,
        fallback_routing_target=request.fallback_routing_target,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
    )
    state = output["state"]

    # 3단계: 프론트엔드에 필요한 최소 결과만 응답 스키마로 정리한다.
    return ChatResponse(
        answer=output["answer"],
        ticket_id=ticket_id,
        session_id=session_id,
        draft_id=state.get("draft_id"),
        category=state.get("category"),
        ui_category=state.get("ui_category"),
        sub_category=state.get("sub_category"),
        routing_target=state.get("routing_target"),
        review_required=state.get("review_required"),
        safety_passed=state.get("safety_passed"),
    )
