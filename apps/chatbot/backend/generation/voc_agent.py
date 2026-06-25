from __future__ import annotations

from constants import VOC_FIXED_RESPONSE
from observability.langfuse import link_chatbot_trace
from schemas import ChatbotState
from common.observability.langfuse import observe_if_enabled


@observe_if_enabled(
    name="voc_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "voc"],
)
def voc_agent_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "voc"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "routing_target": state.get("routing_target"),
            "query": state.get("normalized_query") or state.get("raw_query"),
        },
    )
    update = {
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
    link_chatbot_trace(
        state,
        tags=["feature:generation", "voc"],
        metadata_source={**state, **update},
        output_payload=update,
    )
    return update
