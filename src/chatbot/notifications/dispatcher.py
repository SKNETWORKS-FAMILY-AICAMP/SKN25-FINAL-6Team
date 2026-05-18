from __future__ import annotations

from typing import Any

from chatbot.notifications.slack import send_slack_alert
from chatbot.observability.logger import EVENT_NOTIFICATION_DISPATCHED, log_event


def _urgent_alert_message(state: dict[str, Any]) -> str:
    content = state.get("cleaned_content") or state.get("raw_content") or ""
    final_answer = state.get("final_answer") or ""
    return (
        "[긴급 문의 알림]\n"
        f"ticket_id: {state.get('ticket_id')}\n"
        f"session_id: {state.get('session_id')}\n"
        f"category: {state.get('category')}\n"
        f"routing_target: {state.get('routing_target')}\n"
        f"content: {content}\n"
        f"final_answer: {final_answer}"
    )


def dispatch_urgent_alert(state: dict[str, Any]) -> dict[str, Any]:
    """Dispatch urgent chatbot state to notification channels."""
    if state.get("routing_target") != "urgent_alert":
        return {"status": "skipped", "reason": "routing_target is not urgent_alert"}

    result = send_slack_alert(_urgent_alert_message(state))
    log_event(
        EVENT_NOTIFICATION_DISPATCHED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="final_response",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status=result.get("status", "unknown"),
        metadata={"channel": "slack", "result": result},
    )
    return result
