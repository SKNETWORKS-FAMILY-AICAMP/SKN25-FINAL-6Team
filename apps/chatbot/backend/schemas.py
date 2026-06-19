from __future__ import annotations

from typing import Any, Literal

from langchain.agents import AgentState
from typing_extensions import NotRequired


Category = Literal["payment", "bug", "faq", "voc"]
RoutingTarget = Literal["rag_reply", "payment_agent", "bug_agent", "faq_agent", "voc_agent"]
SafetyAction = Literal[
    "AUTO_RESPONSE",
    "MASKING",
    "SAFE_FALLBACK",
    "BLOCK_RESPONSE",
    "REVIEW_REQUIRED",
]


# LangGraph 전체 노드가 공유하는 state 계약이다.
# 전처리 -> 라우팅 -> agent -> 저장 -> safety -> ticket_completion 순서로 값이 채워진다.
class ChatbotState(AgentState):
    # Request/session metadata.
    user_id: NotRequired[int]
    session_id: NotRequired[str]
    account_id: NotRequired[int | None]
    source_type: NotRequired[str]

    # Active user inquiry.
    raw_query: NotRequired[str]
    masked_content: NotRequired[str]
    input_masked: NotRequired[bool]
    input_detected_labels: NotRequired[list[str]]
    normalized_query: NotRequired[str]

    # Routing and workflow state.
    ticket_id: NotRequired[int]
    ui_category: NotRequired[str | None]
    sub_category: NotRequired[str | None]
    category: NotRequired[Category | str]
    routing_target: NotRequired[RoutingTarget | str]
    fallback_routing_target: NotRequired[str | None]
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
    reasoning_node: NotRequired[str | None]
    retrieval_query: NotRequired[str | None]
    retrieval_enrichment: NotRequired[dict[str, Any] | None]
    retrieved_documents: NotRequired[list[dict[str, Any]]]
    retrieved_count: NotRequired[int]
    retrieval_cache_enabled: NotRequired[bool | None]
    retrieval_cache_hit: NotRequired[bool | None]
    retrieval_cache_backend: NotRequired[str | None]
    retrieval_cache_key_hash: NotRequired[str | None]
    retrieval_cache_ttl: NotRequired[int | None]
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
    notification_result: NotRequired[dict[str, Any] | None]

    # Bug reproduction collection state.
    initial_bug_query: NotRequired[str | None]
    bug_collection_status: NotRequired[str | None]
    bug_report_form: NotRequired[str | None]
    github_issue_content: NotRequired[str | None]

    # Multi-turn bookkeeping.
    retry_count: NotRequired[int]
    conversation_summary: NotRequired[str | None]
    turn_count: NotRequired[int]
