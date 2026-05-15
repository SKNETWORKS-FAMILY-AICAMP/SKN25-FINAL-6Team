from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from langgraph.graph import add_messages
from typing_extensions import TypedDict


class ChatbotState(TypedDict):
    messages: Annotated[list[Any], add_messages]

    user_id: str
    session_id: str
    account_id: int | None
    source_type: str

    raw_content: str
    cleaned_content: str

    ticket_id: int
    category: str
    routing_target: str
    risk_level: str
    sentiment: str

    draft_id: int | None
    answer_draft: str | None
    safety_passed: bool | None
    retry_count: int


@dataclass
class OrchestratorOutput:
    ticket_id: int
    category: str        # 결제 / 인게임버그 / FAQ / VOC
    routing_target: str  # rag_reply / urgent_alert


@dataclass
class PaymentAgentInput:
    ticket_id: int


@dataclass
class SafetyInput:
    draft_id: int
    ticket_id: int
