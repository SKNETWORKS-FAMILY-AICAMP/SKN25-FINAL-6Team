from __future__ import annotations

from chatbot.constants import MAX_MASKING_RETRY, MAX_SAFETY_RETRY
from chatbot.schemas import ChatbotState


CATEGORY_NODE_BY_NAME = {
    "payment": "payment_agent",
    "bug": "bug_agent",
    "faq": "faq_agent",
    "voc": "voc_agent",
    "결제": "payment_agent",
    "인게임/버그": "bug_agent",
    "FAQ": "faq_agent",
    "VOC": "voc_agent",
}


def _is_voc_state(state: ChatbotState) -> bool:
    category = str(state.get("category") or "").strip().lower()
    return category == "voc" or state.get("reasoning_node") == "voc_agent"


def route_by_category(state: ChatbotState) -> str:
    """Route to the concrete category node selected by the request category."""
    category = state["category"]
    return CATEGORY_NODE_BY_NAME.get(str(category), "voc_agent")


def route_after_draft_persistence(state: ChatbotState) -> str:
    """Skip safety scoring for fixed VOC responses, otherwise run safety."""
    if _is_voc_state(state):
        return "final_response"
    return "safety_layer"


def route_after_safety(state: ChatbotState) -> str:
    """Return to the concrete category node on retry, or finish when safety passes/exhausts."""
    if _is_voc_state(state):
        return "final_response"
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
