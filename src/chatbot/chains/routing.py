from __future__ import annotations

from chatbot.constants import MAX_MASKING_RETRY, MAX_SAFETY_RETRY
from chatbot.schemas import ChatbotState


CATEGORY_NODE_BY_NAME = {
    "결제": "payment_agent",
    "인게임/버그": "bug_agent",
    "FAQ": "faq_agent",
    "VOC": "voc_agent",
}


def route_by_category(state: ChatbotState) -> str:
    """Route to the concrete category node selected by the orchestrator."""
    category = state["category"]
    return CATEGORY_NODE_BY_NAME.get(str(category), "voc_agent")


def route_after_safety(state: ChatbotState) -> str:
    """Return to the concrete category node on retry, or finish when safety passes/exhausts."""
    if state.get("safety_action") == "MASKING":
        if state.get("retry_count", 0) <= MAX_MASKING_RETRY:
            return "draft_persistence"
        return "final_response"
    if state.get("safety_action") in {"BLOCK_RESPONSE", "SAFE_FALLBACK", "REVIEW_QUEUE"}:
        return "final_response"
    if state["safety_passed"]:
        return "final_response"
    if state["retry_count"] >= MAX_SAFETY_RETRY:
        return "final_response"
    return route_by_category(state)
