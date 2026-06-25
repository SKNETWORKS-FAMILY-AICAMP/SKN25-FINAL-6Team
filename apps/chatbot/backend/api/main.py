from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from common.db.connection import db_connection
from common.observability.langfuse import configure_langfuse, shutdown_langfuse
from common.retrieval.cache_store import get_cached_session_state, set_cached_session_state

configure_langfuse("chatbot", default_tags=["chatbot", "api"])

from constants import DEFAULT_DEMO_USER_ID
from service.account_service import get_server_regions, login_with_credentials
from service.chatbot_service import run_chatbot
from service.multiturn_service import build_session_context
from utils.config_loader import load_chatbot_yaml


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


@app.on_event("shutdown")
def _shutdown_langfuse_client() -> None:
    shutdown_langfuse()

ChatCategory = Literal["payment", "bug", "faq", "voc"]

# 생성 ID는 작은 fixture/test ID와 구분하기 쉽도록 9자리 숫자 범위에서 만든다.
# DB integer 컬럼 범위 안에 머물면서도 사람이 로그에서 식별하기 쉬운 값이다.
NUMERIC_ID_MIN_VALUE = 100_000_000
NUMERIC_ID_RANDOM_SPAN = 800_000_000
# 랜덤 ID 충돌 가능성은 낮지만, DB 확인 횟수는 제한해 요청 지연을 막는다.
TICKET_ID_COLLISION_RETRY_LIMIT = 8
# 세션 캐시와 멀티턴 context가 과도하게 커지지 않도록 제한한다.
SESSION_TEXT_CLIP_CHARS = 1200
SESSION_DOCUMENT_META_LIMIT = 5
DEFAULT_SESSION_MAX_MESSAGES = 40
DEFAULT_RECENT_SESSION_TURNS = 3

# 문의 내역 화면은 첫 진입 시 최근 20건만 보여주고, 한 번에 최대 100건까지만 조회한다.
DEFAULT_TICKET_HISTORY_LIMIT = 20
MAX_TICKET_HISTORY_LIMIT = 100

class ChatRequest(BaseModel):
    ticket_id: int | None = None
    user_message: str = Field(min_length=1)
    category: ChatCategory
    account_id: int | None = None
    # Demo fallback; authenticated clients should send the logged-in user's real user_id.
    user_id: int = DEFAULT_DEMO_USER_ID
    session_id: str | int | None = None
    source_type: str = "chatbot"
    ui_category: str | None = None
    sub_category: str | None = None
    routing_target: str | None = None
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
    return NUMERIC_ID_MIN_VALUE + secrets.randbelow(NUMERIC_ID_RANDOM_SPAN)


def _new_ticket_id() -> int:
    # 프론트가 ticket_id를 만들지 않도록, 서버에서 충돌 가능성이 낮은 숫자 ID를 생성한다.
    for _ in range(TICKET_ID_COLLISION_RETRY_LIMIT):
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
    # 같은 상담 흐름은 session base를 유지하고, 새 문의 turn마다 뒤 번호만 증가시킨다.
    if not previous_session_id:
        return f"{_new_numeric_id()}-1"

    session_id = str(previous_session_id).strip()
    if not session_id:
        return f"{_new_numeric_id()}-1"

    base, separator, turn = session_id.rpartition("-")
    if separator and base and turn.isdigit():
        return f"{base}-{int(turn) + 1}"
    return f"{session_id}-1"


def _clip_session_text(value: Any, limit: int = SESSION_TEXT_CLIP_CHARS) -> str:
    text = " ".join(str(value or "").replace("\\n", "\n").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _session_messages_from_cache(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages = payload.get("previous_messages")
    if not isinstance(messages, list):
        return []
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = _clip_session_text(message.get("content"), SESSION_TEXT_CLIP_CHARS)
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized


def _document_session_meta(documents: Any, limit: int = SESSION_DOCUMENT_META_LIMIT) -> list[dict[str, Any]]:
    if not isinstance(documents, list):
        return []
    result: list[dict[str, Any]] = []
    for document in documents[:limit]:
        if not isinstance(document, dict):
            continue
        result.append(
            {
                "document_id": document.get("document_id") or document.get("documents_id"),
                "chunk_id": document.get("chunk_id"),
                "title": document.get("title"),
                "source_type": document.get("source_type"),
                "category": document.get("category"),
                "published_at": document.get("published_at"),
                "updated_at": document.get("updated_at"),
            }
        )
    return result


def _build_session_cache_payload(
    *,
    request: ChatRequest,
    session_id: str,
    previous_messages: list[dict[str, str]] | None,
    answer: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    max_messages = int(os.environ.get("CHATBOT_SESSION_MAX_MESSAGES", str(DEFAULT_SESSION_MAX_MESSAGES)))
    messages = list(previous_messages or [])
    messages.extend(
        [
            {"role": "user", "content": _clip_session_text(request.user_message)},
            {"role": "assistant", "content": _clip_session_text(answer)},
        ]
    )
    messages = messages[-max_messages:]
    return {
        "session_id": session_id,
        "user_id": request.user_id,
        "account_id": request.account_id,
        "previous_messages": messages,
        "conversation_summary": state.get("conversation_summary"),
        "last_category": state.get("category"),
        "last_ui_category": state.get("ui_category"),
        "last_sub_category": state.get("sub_category"),
        "last_routing_target": state.get("routing_target"),
        "last_retrieval_query": state.get("retrieval_query"),
        "last_retrieved_documents": _document_session_meta(state.get("retrieved_documents")),
        "last_answer": _clip_session_text(answer),
    }


def _is_bug_route(request: ChatRequest) -> bool:
    return (
        request.category == "bug"
        or str(request.routing_target or "").strip().lower() == "bug_agent"
    )


def _initial_bug_query_from_messages(messages: list[dict[str, str]] | None) -> str:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content and not _looks_like_bug_report_form(content):
            return content
    return ""


def _bug_report_form_config() -> dict[str, Any]:
    return load_chatbot_yaml("forms/bug_report.yaml")


def _bug_report_form_aliases() -> tuple[str, ...]:
    raw_aliases = _bug_report_form_config().get("aliases")
    if not isinstance(raw_aliases, list) or not all(isinstance(label, str) for label in raw_aliases):
        raise ValueError("forms/bug_report.yaml:aliases must be list[str]")
    return tuple(raw_aliases)


def _bug_report_form_min_label_matches() -> int:
    value = _bug_report_form_config().get("min_label_matches", 2)
    if not isinstance(value, int):
        raise ValueError("forms/bug_report.yaml:min_label_matches must be an integer")
    return value


def _looks_like_bug_report_form(text: str) -> bool:
    return sum(1 for label in _bug_report_form_aliases() if label in text) >= _bug_report_form_min_label_matches()


@app.get("/health")
def health() -> dict[str, str]:
    # 배포/헬스체크에서 API 프로세스가 살아 있는지만 빠르게 확인한다.
    return {"status": "ok"}


@app.get("/server-regions")
def server_regions() -> dict[str, list[str]]:
    # 로그인 화면의 서버 선택 목록은 DB 값을 우선 사용하고, 실패 시 service 계층에서 기본값으로 보정한다.
    return {"items": get_server_regions()}


@app.get("/config")
def chatbot_config() -> dict[str, Any]:
    return {
        "category_tree": load_chatbot_yaml("ui/categories.yaml").get("category_tree", {}),
        "recommended_faq": load_chatbot_yaml("ui/recommended_faq.yaml").get("recommended_faq", {}),
        "bug_report_form": _bug_report_form_config(),
    }


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    # 이메일/비밀번호/서버로 게임 계정을 검증하고 user_id/account_id를 프론트에 돌려준다.
    result = login_with_credentials(request.email, request.password, request.server_region)
    return LoginResponse(**result)


@app.get("/tickets", response_model=list[InquiryHistoryItem])
def list_tickets(
    user_id: int = Query(..., ge=1),
    account_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=DEFAULT_TICKET_HISTORY_LIMIT, ge=1, le=MAX_TICKET_HISTORY_LIMIT),
) -> list[InquiryHistoryItem]:
    # 문의 내역 화면은 qa_ticket의 최신 chatbot 문의를 읽고, raw_query 안의 AI 답변을 분리해 표시한다.
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
    session_id = _next_session_turn_id(request.session_id)
    initial_bug_query: str | None = None
    bug_report_form: str | None = None
    ticket_id = _new_ticket_id()

    # 이전 대화가 요청에 없으면 DB에서 같은 session base의 최근 turn을 가져와 멀티턴 context로 사용한다.
    session_cache = get_cached_session_state(session_id)
    cached_messages = _session_messages_from_cache(session_cache)
    previous_messages = cached_messages or request.previous_messages
    conversation_summary = request.conversation_summary or session_cache.get("conversation_summary")
    if previous_messages is None:
        context = build_session_context(
            session_id=session_id,
            user_id=request.user_id,
            account_id=request.account_id,
            current_ticket_id=ticket_id,
            recent_turns=DEFAULT_RECENT_SESSION_TURNS,
        )
        previous_messages = context.previous_messages
        conversation_summary = conversation_summary or context.conversation_summary

    if _is_bug_route(request):
        if _looks_like_bug_report_form(request.user_message):
            initial_bug_query = _initial_bug_query_from_messages(previous_messages)
            bug_report_form = request.user_message
        else:
            initial_bug_query = request.user_message

    # chatbot_service가 LangGraph workflow를 실행하고 최종 답변과 state를 반환한다.
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
        fallback_routing_target=request.fallback_routing_target,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
        initial_bug_query=initial_bug_query,
        bug_report_form=bug_report_form,
    )
    state = output["state"]
    set_cached_session_state(
        session_id,
        _build_session_cache_payload(
            request=request,
            session_id=session_id,
            previous_messages=previous_messages,
            answer=output["answer"],
            state=state,
        ),
    )

    # 프론트에는 화면 갱신에 필요한 최소 결과만 응답한다.
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
