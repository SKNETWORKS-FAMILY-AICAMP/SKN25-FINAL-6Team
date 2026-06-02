from __future__ import annotations

from typing import Any

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_qa_ticket


SUPPORTED_CATEGORIES = {"payment", "bug", "faq", "voc"}


def _normalize_text(text: str) -> str:
    """Normalize whitespace before category-specific handling."""
    return " ".join(text.strip().split())


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
    enriched_query = _normalize_text(raw_query)
    category = _category_from_user_selection(state.get("category"))
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
                "status": "open",
            },
        }
    )

    return {
        "ticket_id": ticket_id,
        "enriched_query": enriched_query,
        "category": category,
        "routing_target": routing_target,
        "classification_method": "user_selected",
        "classification_reason": "category selected by user",
        "is_actionable": True,
        "should_use_rag": category == "faq",
        "fallback_reason": None,
    }
