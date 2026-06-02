from __future__ import annotations

from typing import Any, Literal

from langchain.agents import AgentState
from pydantic import BaseModel
from typing_extensions import NotRequired


Category = Literal["payment", "bug", "faq", "voc", "결제", "인게임/버그", "FAQ", "VOC"]
RoutingTarget = Literal["rag_reply", "urgent_alert"]
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
    masked_content: NotRequired[str]
    input_masked: NotRequired[bool]
    input_detected_labels: NotRequired[list[str]]
    normalized_query: NotRequired[str]
    enriched_query: NotRequired[str]

    # Routing and workflow state.
    ticket_id: NotRequired[int]
    category: NotRequired[Category | str]
    routing_target: NotRequired[RoutingTarget | str]
    is_actionable: NotRequired[bool | None]
    should_use_rag: NotRequired[bool | None]
    fallback_reason: NotRequired[str | None]

    # Drafting, retrieval, safety, and review state.
    draft_id: NotRequired[int | None]
    draft_text: NotRequired[str | None]
    draft_persistence_result: NotRequired[dict[str, Any] | None]
    evidence_count: NotRequired[int]
    evidence_results: NotRequired[list[dict[str, Any]]]
    final_text: NotRequired[str | None]
    final_response_result: NotRequired[dict[str, Any] | None]
    reasoning_node: NotRequired[str | None]
    query_enrichment_method: NotRequired[str | None]
    query_enrichment_terms: NotRequired[list[str]]
    retrieval_query: NotRequired[str | None]
    retrieval_enrichment: NotRequired[dict[str, Any] | None]
    retrieved_documents: NotRequired[list[dict[str, Any]]]
    payment_context: NotRequired[dict[str, Any] | None]
    faq_failure_reason: NotRequired[str | None]
    safety_passed: NotRequired[bool | None]
    safety_action: NotRequired[SafetyAction | str | None]
    safety_reason: NotRequired[str | None]
    safety_result: NotRequired[dict[str, Any] | None]
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


class PaymentAgentInput(BaseModel):
    """Minimal contract for a payment reasoning agent or graph node."""

    ticket_id: int
    account_id: int | None = None
    normalized_query: str | None = None
    enriched_query: str | None = None


class SafetyInput(BaseModel):
    """Minimal contract for a safety scoring or decision node."""

    draft_id: int | None = None
    ticket_id: int
    draft_text: str | None = None


class SafetyDecision(BaseModel):
    """Structured safety branch decision for graph-ready workflows."""

    safety_passed: bool
    action: SafetyAction
    reason: str
    retry_recommended: bool = False
