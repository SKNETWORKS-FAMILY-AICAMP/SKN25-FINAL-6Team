from __future__ import annotations

import json

from chatbot.generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    REVIEW_QUEUE_RESPONSE,
    fallback_response_for_category,
)
from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.observability.logger import EVENT_FINAL_RESPONSE_CREATED, log_event
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import update_qa_ticket_status, write_final_response, write_insight


def _ticket_status_for_decision(decision: str) -> str:
    if decision == "REVIEW_QUEUE":
        return "review_required"
    if decision == "BLOCK_RESPONSE":
        return "blocked"
    return "answered"


def _pattern_risk_level(state: ChatbotState, decision: str) -> str:
    if state.get("routing_target") == "urgent_alert" or decision == "REVIEW_QUEUE":
        return "high"
    if decision in ("SAFE_FALLBACK", "BLOCK_RESPONSE"):
        return "medium"
    return "low"


def final_response_node(state: ChatbotState) -> dict:
    decision = state["safety_action"]
    draft_text = state["draft_text"]

    if decision == "BLOCK_RESPONSE":
        final_text = BLOCK_RESPONSE
    elif decision in ("SAFE_FALLBACK", "MASKING"):
        final_text = fallback_response_for_category(state.get("category"))
    elif decision == "REVIEW_QUEUE":
        final_text = REVIEW_QUEUE_RESPONSE
    else:
        final_text = draft_text

    notification_result = dispatch_urgent_alert({**state, "final_text": final_text})

    final_response_result = json.loads(write_final_response.invoke({
        "payload": {
            "ticket_id": state["ticket_id"],
            "draft_id": state.get("draft_id"),
            "final_text": final_text,
            "safety_action": decision,
        },
    }))
    ticket_status_result = json.loads(update_qa_ticket_status.invoke({
        "payload": {
            "ticket_id": state["ticket_id"],
            "status": _ticket_status_for_decision(decision),
        },
    }))
    insight_result = None
    if state.get("user_id") is not None:
        insight_result = json.loads(write_insight.invoke({
            "payload": {
                "user_id": state.get("user_id"),
                "ticket_id": state["ticket_id"],
                "account_id": state.get("account_id"),
                "content_summary": state.get("classification_reason")
                or state.get("enriched_query")
                or state.get("raw_query"),
                "category": state.get("category"),
                "sentiment": state.get("sentiment") or "neutral",
                "risk_level": "high" if state.get("routing_target") == "urgent_alert" else "normal",
                "pattern_risk_level": _pattern_risk_level(state, decision),
            },
        }))

    log_event(
        EVENT_FINAL_RESPONSE_CREATED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="final_response",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status="ok",
        metadata={
            "safety_action": decision,
            "notification_status": notification_result.get("status"),
            "ticket_status_result": ticket_status_result,
            "insight_result": insight_result,
        },
    )

    return {
        "final_text": final_text,
        "final_response_result": final_response_result,
        "notification_result": notification_result,
        "ticket_status_result": ticket_status_result,
        "insight_result": insight_result,
    }
