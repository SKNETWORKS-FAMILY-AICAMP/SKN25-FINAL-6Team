from __future__ import annotations

from chatbot.constants import MAX_SAFETY_RETRY
from chatbot.schemas import ChatbotState


PAYMENT_CATEGORIES = {"결제", "寃곗젣"}
BUG_CATEGORIES = {"인게임/버그", "?멸쾶?꾨쾭洹?"}


def route_by_category(state: ChatbotState) -> str:
    """Route to the concrete category node selected by the orchestrator."""
    category = state["category"]
    if category in PAYMENT_CATEGORIES:
        return "payment_agent"
    if category in BUG_CATEGORIES:
        return "bug_agent"
    if category == "FAQ":
        return "faq_agent"
    return "voc_agent"


def route_after_safety(state: ChatbotState) -> str:
    """Return to the concrete category node on retry, or finish when safety passes/exhausts."""
    if state["safety_passed"]:
        return "final_response"
    if state["retry_count"] >= MAX_SAFETY_RETRY:
        return "final_response"
    return route_by_category(state)
