from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.common.observability.langsmith import configure_langsmith

configure_langsmith("chatbot")

from chatbot.service.chatbot_service import run_chatbot


app = FastAPI(title="GameOps Chatbot API")


class ChatRequest(BaseModel):
    ticket_id: int
    user_message: str = Field(min_length=1)
    account_id: int | None = None
    user_id: int = 1
    session_id: int = 1
    source_type: str = "chatbot"
    previous_messages: list[dict[str, str]] | None = None


class ChatResponse(BaseModel):
    answer: str
    ticket_id: int
    category: str | None = None
    routing_target: str | None = None
    review_required: bool | None = None
    safety_passed: bool | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    output: dict[str, Any] = run_chatbot(
        ticket_id=request.ticket_id,
        user_message=request.user_message,
        account_id=request.account_id,
        user_id=request.user_id,
        session_id=request.session_id,
        source_type=request.source_type,
        previous_messages=request.previous_messages,
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
