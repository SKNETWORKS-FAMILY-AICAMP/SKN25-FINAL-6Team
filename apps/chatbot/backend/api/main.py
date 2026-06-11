from __future__ import annotations

import os
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
    ticket_id: int
    user_message: str = Field(min_length=1)
    category: ChatCategory
    account_id: int | None = None
    user_id: int = 1
    session_id: int = 1
    source_type: str = "chatbot"
    previous_messages: list[dict[str, str]] | None = None
    conversation_summary: str | None = None


class ChatResponse(BaseModel):
    answer: str
    ticket_id: int
    category: str | None = None
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/server-regions")
def server_regions() -> dict[str, list[str]]:
    return {"items": get_server_regions()}


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    result = login_with_credentials(request.email, request.password, request.server_region)
    return LoginResponse(**result)


@app.get("/tickets", response_model=list[InquiryHistoryItem])
def list_tickets(
    user_id: int = Query(..., ge=1),
    account_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[InquiryHistoryItem]:
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
                    t.inquiry_created_at,
                    latest_response.final_text
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT fr.final_text
                    FROM final_response fr
                    WHERE fr.ticket_id = t.ticket_id
                    ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
                    LIMIT 1
                ) latest_response ON TRUE
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
            final_text=row[6],
        )
        for row in rows
    ]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    previous_messages = request.previous_messages
    conversation_summary = request.conversation_summary
    if previous_messages is None:
        context = build_session_context(
            session_id=request.session_id,
            user_id=request.user_id,
            account_id=request.account_id,
            current_ticket_id=request.ticket_id,
            recent_turns=3,
        )
        previous_messages = context.previous_messages
        conversation_summary = conversation_summary or context.conversation_summary

    output: dict[str, Any] = run_chatbot(
        ticket_id=request.ticket_id,
        user_message=request.user_message,
        category=request.category,
        account_id=request.account_id,
        user_id=request.user_id,
        session_id=request.session_id,
        source_type=request.source_type,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
    )
    state = output["state"]
    return ChatResponse(
        answer=output["answer"],
        ticket_id=request.ticket_id,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        review_required=state.get("review_required"),
        safety_passed=state.get("safety_passed"),
    )
