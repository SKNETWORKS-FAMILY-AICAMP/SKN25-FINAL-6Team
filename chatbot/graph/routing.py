from __future__ import annotations

from chatbot.constants import MAX_SAFETY_RETRY
from chatbot.schemas import ChatbotState


def route_by_category(state: ChatbotState) -> str:
    """Route to the category agent selected by the orchestrator."""
    category = state.get("category") or "FAQ"
    if category == "결제":
        return "payment_agent"
    if category == "인게임버그":
        return "bug_agent"
    if category == "VOC":
        return "voc_agent"
    return "faq_agent"


def route_after_safety(state: ChatbotState) -> str:
    """Return to the category agent on retry, or finish when safety passes/exhausts."""
    if state.get("safety_passed"):
        return "final_response"
    if state.get("retry_count", 0) >= MAX_SAFETY_RETRY:
        return "final_response"
    return route_by_category(state)

