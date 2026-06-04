from __future__ import annotations

from typing import Any

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_qa_ticket
from chatbot.utils.query_enrichment import normalize_query_text


SUPPORTED_CATEGORIES = {"payment", "bug", "faq", "voc"}


def _category_from_user_selection(value: Any) -> str:
    category = str(value or "").strip().lower()
    if not category:
        raise ValueError("category is required for chatbot routing")
    if category not in SUPPORTED_CATEGORIES:
        allowed = ", ".join(sorted(SUPPORTED_CATEGORIES))
        raise ValueError(f"unsupported category: {category}. allowed: {allowed}")
    return category


def ticket_preprocess_node(state: ChatbotState) -> dict:
    """Normalize the inquiry, store the QA ticket, and trust the user-selected category."""
    ticket_id = state["ticket_id"]
    raw_query = state["raw_query"]
    masked_content = state.get("masked_content") or raw_query
    category = _category_from_user_selection(state.get("category"))
    normalized_query = normalize_query_text(masked_content)
    routing_target = state.get("routing_target") or "rag_reply"

    write_qa_ticket.invoke(
        {
            "payload": {
                "ticket_id": ticket_id,
                "user_id": state["user_id"],
                "account_id": state["account_id"],
                "session_id": state.get("session_id"),
                "raw_query": raw_query,
                "source_type": state["source_type"],
                "status": "pending",
            },
        }
    )

    return {
        "ticket_id": ticket_id,
        "normalized_query": normalized_query,
        "enriched_query": normalized_query,
        "query_enrichment_method": "normalize_only",
        "query_enrichment_terms": [],
        "category": category,
        "routing_target": routing_target,
        "is_actionable": True,
        "should_use_rag": category == "faq",
        "fallback_reason": None,
    }
