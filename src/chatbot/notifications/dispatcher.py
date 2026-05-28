from __future__ import annotations

from typing import Any

from chatbot.notifications.github_issue import create_github_issue
from chatbot.notifications.slack import send_slack_alert
from chatbot.observability.logger import EVENT_NOTIFICATION_DISPATCHED, log_event
from chatbot.repository.notification_repository import notification_log_exists, save_notification_log


BUG_CATEGORY_VALUES = {"?멸쾶??踰꾧렇", "인게임/버그", "인게임버그"}


def _urgent_alert_message(state: dict[str, Any]) -> str:
    content = state.get("enriched_query") or state.get("raw_query") or ""
    final_text = state.get("final_text") or ""
    return (
        "[긴급 문의 알림]\n"
        f"ticket_id: {state.get('ticket_id')}\n"
        f"session_id: {state.get('session_id')}\n"
        f"category: {state.get('category')}\n"
        f"routing_target: {state.get('routing_target')}\n"
        f"content: {content}\n"
        f"final_text: {final_text}"
    )


def _is_in_game_bug_alert(state: dict[str, Any]) -> bool:
    return (
        state.get("routing_target") == "urgent_alert"
        and (
            state.get("reasoning_node") == "bug_agent"
            or str(state.get("category") or "") in BUG_CATEGORY_VALUES
        )
    )


def _github_issue_title(state: dict[str, Any]) -> str:
    content = str(state.get("enriched_query") or state.get("raw_query") or "").strip()
    if len(content) > 60:
        content = f"{content[:57]}..."
    return f"[인게임 버그] {content or '운영자 확인 필요'}"


def _github_issue_body(state: dict[str, Any]) -> str:
    content = state.get("enriched_query") or state.get("raw_query") or ""
    final_text = state.get("final_text") or ""
    return (
        "## Ticket\n"
        f"- ticket_id: {state.get('ticket_id')}\n"
        f"- session_id: {state.get('session_id')}\n"
        f"- user_id: {state.get('user_id')}\n"
        f"- account_id: {state.get('account_id')}\n"
        f"- category: {state.get('category')}\n"
        f"- routing_target: {state.get('routing_target')}\n"
        f"- reasoning_node: {state.get('reasoning_node')}\n\n"
        "## Inquiry\n"
        f"{content}\n\n"
        "## Final Response\n"
        f"{final_text}\n"
    )


def _dispatch_github_issue_for_bug(state: dict[str, Any]) -> dict[str, Any]:
    if not _is_in_game_bug_alert(state):
        return {"status": "skipped", "reason": "not an in-game urgent bug alert"}

    title = _github_issue_title(state)
    body = _github_issue_body(state)
    result = create_github_issue(title, body)
    notification_log_result = save_notification_log(
        {
            "ticket_id": state.get("ticket_id"),
            "channel": "github_issue",
            "status": result.get("status", "unknown"),
            "message": result.get("issue_url") or title,
            "error_message": result.get("message") if result.get("status") == "error" else None,
            "error_category": result.get("error_category"),
        }
    )
    return {**result, "notification_log_result": notification_log_result}


def _dispatch_slack_review_alert(state: dict[str, Any], message: str) -> dict[str, Any]:
    if state.get("safety_action") != "REVIEW_QUEUE":
        return {"status": "skipped", "reason": "safety_action is not REVIEW_QUEUE"}

    existing_log = notification_log_exists(state.get("ticket_id"), "slack")
    if existing_log.get("exists"):
        return {"status": "skipped", "reason": "slack alert already sent for ticket_id"}

    result = send_slack_alert(message)
    notification_log_result = save_notification_log(
        {
            "ticket_id": state.get("ticket_id"),
            "channel": "slack",
            "status": result.get("status", "unknown"),
            "message": message,
            "error_message": result.get("message") if result.get("status") == "error" else None,
            "error_category": result.get("error_category"),
        }
    )
    return {**result, "notification_log_result": notification_log_result}


def dispatch_urgent_alert(state: dict[str, Any]) -> dict[str, Any]:
    """Dispatch urgent chatbot state to notification channels."""
    if state.get("routing_target") != "urgent_alert":
        return {"status": "skipped", "reason": "routing_target is not urgent_alert"}

    message = _urgent_alert_message(state)
    slack_result = _dispatch_slack_review_alert(state, message)
    github_issue_result = _dispatch_github_issue_for_bug(state)
    log_event(
        EVENT_NOTIFICATION_DISPATCHED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="final_response",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status=slack_result.get("status", "unknown"),
        error_category=slack_result.get("error_category"),
        metadata={
            "channel": "slack",
            "result": slack_result,
            "github_issue_result": github_issue_result,
        },
    )
    return {
        **slack_result,
        "github_issue_result": github_issue_result,
    }
