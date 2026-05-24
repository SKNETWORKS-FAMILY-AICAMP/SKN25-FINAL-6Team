from __future__ import annotations

from typing import Any, Literal

from langchain.agents import AgentState
from pydantic import BaseModel
from typing_extensions import NotRequired

Category = Literal["결제", "인게임/버그", "FAQ", "VOC"]
RoutingTarget = Literal["rag_reply", "urgent_alert"]
RoutingIntentName = Literal[
    "payment_how_to",
    "payment_missing_item",
    "refund_request",
    "payment_dispute",
    "bug_how_to",
    "bug_account_specific",
    "policy_question",
    "faq_question",
    "voc",
]
SafetyAction = Literal[
    "AUTO_RESPONSE",
    "MASKING",
    "SAFE_FALLBACK",
    "BLOCK_RESPONSE",
    "REVIEW_QUEUE",
]


class ChatbotState(AgentState):
    """Runtime state shared by category nodes and the StateGraph workflow."""

    # Request/session metadata.
    user_id: NotRequired[int]
    session_id: NotRequired[int]
    account_id: NotRequired[int | None]
    source_type: NotRequired[str]

    # Active user inquiry.
    raw_query: NotRequired[str]
    enriched_query: NotRequired[str]

    # Routing and workflow state.
    ticket_id: NotRequired[int]
    category: NotRequired[Category | str]
    routing_target: NotRequired[RoutingTarget | str]
    classification_method: NotRequired[str | None]
    classification_reason: NotRequired[str | None]
    is_actionable: NotRequired[bool | None]
    should_use_rag: NotRequired[bool | None]
    fallback_reason: NotRequired[str | None]

    # Drafting, retrieval, safety, and review state.
    analysis_id: NotRequired[int | None]
    draft_id: NotRequired[int | None]
    draft_text: NotRequired[str | None]
    final_text: NotRequired[str | None]
    final_response_result: NotRequired[dict[str, Any] | None]
    reasoning_node: NotRequired[str | None]
    retrieval_query: NotRequired[str | None]
    retrieval_enrichment: NotRequired[dict[str, Any] | None]
    retrieved_documents: NotRequired[list[dict[str, Any]]]
    payment_context: NotRequired[dict[str, Any] | None]
    faq_failure_reason: NotRequired[str | None]
    safety_passed: NotRequired[bool | None]
    safety_action: NotRequired[SafetyAction | str | None]
    safety_reason: NotRequired[str | None]
    factuality_score: NotRequired[float | None]
    hallucination_score: NotRequired[float | None]
    toxicity_score: NotRequired[float | None]
    policy_violation_score: NotRequired[float | None]
    review_required: NotRequired[bool | None]
    masking_applied: NotRequired[bool | None]
    masking_labels: NotRequired[list[str]]
    voc_type: NotRequired[str | None]
    sentiment: NotRequired[str | None]
    topic_keywords: NotRequired[list[str]]
    notification_result: NotRequired[dict[str, Any] | None]

    # Multi-turn bookkeeping.
    retry_count: NotRequired[int]
    conversation_summary: NotRequired[str | None]
    turn_count: NotRequired[int]


class OrchestratorOutput(BaseModel):
    """Structured routing result returned by the LLM classifier."""

    ticket_id: int
    category: Category
    routing_target: RoutingTarget
    reason: str


class RoutingIntent(BaseModel):
    """Normalized user intent used before final category routing."""

    intent: RoutingIntentName
    normalized_query: str
    is_actionable: bool = True
    requires_account_lookup: bool = False
    should_use_rag: bool = False
    fallback_reason: str | None = None
    reason: str


class PaymentAgentInput(BaseModel):
    """Minimal contract for a payment reasoning agent or graph node."""

    ticket_id: int
    account_id: int | None = None
    enriched_query: str | None = None


class SafetyInput(BaseModel):
    """Minimal contract for a safety scoring or decision node."""

    draft_id: int
    ticket_id: int
    draft_text: str | None = None


class SafetyDecision(BaseModel):
    """Structured safety branch decision for graph-ready workflows."""

    safety_passed: bool
    action: SafetyAction
    reason: str
    retry_recommended: bool = False
