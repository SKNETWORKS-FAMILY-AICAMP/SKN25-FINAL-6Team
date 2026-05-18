from __future__ import annotations

from typing import Literal

from langchain.agents import AgentState
from pydantic import BaseModel
from typing_extensions import NotRequired

Category = Literal["결제", "인게임버그", "FAQ", "VOC"]
RoutingTarget = Literal["rag_reply", "urgent_alert"]
SafetyAction = Literal[
    "AUTO_RESPONSE",
    "MASKING",
    "SAFE_FALLBACK",
    "BLOCK_RESPONSE",
    "REVIEW_QUEUE",
]


class ChatbotState(AgentState):
    """Runtime state shared by the create_agent baseline and future StateGraph nodes."""

    # Request/session metadata.
    user_id: NotRequired[str]
    session_id: NotRequired[str]
    account_id: NotRequired[int | None]
    source_type: NotRequired[str]

    # Active user inquiry.
    raw_content: NotRequired[str]
    cleaned_content: NotRequired[str]

    # Routing and workflow state.
    ticket_id: NotRequired[int]
    category: NotRequired[Category | str]
    routing_target: NotRequired[RoutingTarget | str]
    classification_method: NotRequired[str | None]
    classification_reason: NotRequired[str | None]

    # Drafting, safety, and review state.
    draft_id: NotRequired[int | None]
    answer_draft: NotRequired[str | None]
    final_answer: NotRequired[str | None]
    reasoning_node: NotRequired[str | None]
    safety_passed: NotRequired[bool | None]
    safety_action: NotRequired[SafetyAction | str | None]
    safety_reason: NotRequired[str | None]
    review_required: NotRequired[bool | None]
    voc_type: NotRequired[str | None]
    voc_sentiment: NotRequired[str | None]
    voc_topic_keywords: NotRequired[list[str]]

    # Multi-turn bookkeeping.
    retry_count: NotRequired[int]
    conversation_summary: NotRequired[str | None]
    turn_count: NotRequired[int]


class OrchestratorOutput(BaseModel):
    """Structured routing result that can be reused by a future orchestrator node."""

    ticket_id: int
    category: Category
    routing_target: RoutingTarget
    reason: str


class PaymentAgentInput(BaseModel):
    """Minimal contract for a payment reasoning agent or graph node."""

    ticket_id: int
    account_id: int | None = None
    cleaned_content: str | None = None


class SafetyInput(BaseModel):
    """Minimal contract for a safety scoring or decision node."""

    draft_id: int
    ticket_id: int
    answer_draft: str | None = None


class SafetyDecision(BaseModel):
    """Structured safety branch decision for graph-ready workflows."""

    safety_passed: bool
    action: SafetyAction
    reason: str
    retry_recommended: bool = False
