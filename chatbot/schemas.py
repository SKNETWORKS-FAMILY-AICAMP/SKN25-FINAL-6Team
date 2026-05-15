from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain.agents import AgentState
from typing_extensions import NotRequired


class ChatbotState(AgentState):
    user_id: NotRequired[str]
    session_id: NotRequired[str]
    account_id: NotRequired[int | None]
    source_type: NotRequired[str]

    raw_content: NotRequired[str]
    cleaned_content: NotRequired[str]

    ticket_id: NotRequired[int]
    category: NotRequired[str]
    routing_target: NotRequired[str]
    risk_level: NotRequired[str]
    sentiment: NotRequired[str]

    draft_id: NotRequired[int | None]
    answer_draft: NotRequired[str | None]
    safety_passed: NotRequired[bool | None]
    retry_count: NotRequired[int]


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
