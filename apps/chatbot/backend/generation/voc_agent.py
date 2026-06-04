from __future__ import annotations

from chatbot.constants import VOC_FIXED_RESPONSE
from chatbot.schemas import ChatbotState


def voc_agent_node(state: ChatbotState) -> dict:
    return {
        "draft_text": VOC_FIXED_RESPONSE,
        "draft_id": state.get("draft_id"),
        "retry_count": state["retry_count"],
        "category": state.get("category") or "voc",
        "routing_target": state["routing_target"],
        "reasoning_node": "voc_agent",
        "safety_passed": True,
        "safety_action": "AUTO_RESPONSE",
        "safety_reason": "VOC fixed response.",
    }
