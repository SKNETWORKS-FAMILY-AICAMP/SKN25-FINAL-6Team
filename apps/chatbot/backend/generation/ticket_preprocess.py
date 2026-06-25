from __future__ import annotations

from typing import Any

from generation.response.fixed_responses import BLOCK_RESPONSE
from observability.langfuse import link_chatbot_trace
from repository.ticket_repository import save_qa_ticket
from schemas import ChatbotState
from utils.query_enrichment import normalize_query_text
from common.observability.langfuse import observe_if_enabled


SUPPORTED_CATEGORIES = {"payment", "bug", "faq", "voc"}
CATEGORY_DEFAULT_ROUTING_TARGET = {
    "payment": "payment_agent",
    "bug": "bug_agent",
    "faq": "faq_agent",
    "voc": "voc_agent",
}
write_qa_ticket = save_qa_ticket


def _write_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    target = write_qa_ticket
    if hasattr(target, "invoke"):
        return target.invoke({"payload": payload})
    return target(payload)


def _category_from_user_selection(value: Any) -> str:
    category = str(value or "").strip().lower()
    if not category:
        raise ValueError("category is required for chatbot routing")
    if category not in SUPPORTED_CATEGORIES:
        allowed = ", ".join(sorted(SUPPORTED_CATEGORIES))
        raise ValueError(f"unsupported category: {category}. allowed: {allowed}")
    return category


@observe_if_enabled(
    name="ticket_preprocess",
    as_type="chain",
    tags=["chatbot", "feature:preprocess"],
)
def ticket_preprocess_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:preprocess"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "category": state.get("category"),
            "routing_target": state.get("routing_target"),
            "source_type": state.get("source_type"),
        },
    )

    ticket_id = state["ticket_id"]
    raw_query = state["raw_query"]
    masked_content = state.get("masked_content") or raw_query
    category = _category_from_user_selection(state.get("category"))
    normalized_query = normalize_query_text(masked_content)
    routing_target = state.get("routing_target") or CATEGORY_DEFAULT_ROUTING_TARGET[category]

    _write_qa_ticket(
        {
            "ticket_id": ticket_id,
            "user_id": state["user_id"],
            "account_id": state["account_id"],
            "session_id": state.get("session_id"),
            "raw_query": raw_query,
            "source_type": state["source_type"],
            "status": "pending",
        }
    )

    if "prompt_injection" in (state.get("input_detected_labels") or []):
        update = {
            "ticket_id": ticket_id,
            "normalized_query": normalized_query,
            "category": category,
            "routing_target": routing_target,
            "is_actionable": False,
            "fallback_reason": "prompt_injection_detected",
            "draft_text": BLOCK_RESPONSE,
            "safety_action": "BLOCK_RESPONSE",
            "safety_passed": False,
            "retry_count": 0,
        }
        link_chatbot_trace(
            state,
            tags=["feature:preprocess"],
            metadata_source={**state, **update},
            output_payload=update,
        )
        return update

    update = {
        "ticket_id": ticket_id,
        "normalized_query": normalized_query,
        "ui_category": state.get("ui_category"),
        "sub_category": state.get("sub_category"),
        "category": category,
        "routing_target": routing_target,
        "fallback_routing_target": state.get("fallback_routing_target"),
        "is_actionable": True,
        "fallback_reason": None,
    }
    link_chatbot_trace(
        state,
        tags=["feature:preprocess"],
        metadata_source={**state, **update},
        output_payload=update,
    )
    return update
