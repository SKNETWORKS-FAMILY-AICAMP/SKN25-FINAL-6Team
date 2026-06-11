from __future__ import annotations

from typing import Any

from chatbot.notifications.github_issue import create_github_issue
from chatbot.notifications.slack import send_slack_alert
from chatbot.observability.logger import EVENT_NOTIFICATION_DISPATCHED, log_event
from chatbot.repository.notification_repository import notification_log_exists, save_notification_log


BUG_CATEGORY_VALUES = {"bug", "인게임/버그", "인게임버그"}


# 알림 메시지에는 원문보다 전처리된 normalized_query를 우선 사용한다.
def _inquiry_content(state: dict[str, Any]) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "")


# Slack/GitHub로 보낼 긴급 알림 본문을 workflow state에서 조립한다.
def _urgent_alert_message(state: dict[str, Any]) -> str:
    content = _inquiry_content(state)
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


# urgent_alert 중에서도 인게임 버그 성격일 때만 GitHub issue 생성 대상으로 본다.
def _is_in_game_bug_alert(state: dict[str, Any]) -> bool:
    return (
        state.get("routing_target") == "urgent_alert"
        and (
            state.get("reasoning_node") == "bug_agent"
            or str(state.get("category") or "") in BUG_CATEGORY_VALUES
        )
    )


# GitHub issue 목록에서 식별하기 쉽도록 문의 앞부분을 제목으로 만든다.
def _github_issue_title(state: dict[str, Any]) -> str:
    content = _inquiry_content(state).strip()
    if len(content) > 60:
        content = f"{content[:57]}..."
    return f"[인게임 버그] {content or '운영자 확인 필요'}"


# 운영자가 재현 정보와 최종 응답을 함께 볼 수 있게 issue body를 구성한다.
def _github_issue_body(state: dict[str, Any]) -> str:
    content = _inquiry_content(state)
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


# 인게임 긴급 버그 문의는 GitHub issue로 남기고 notification_log에 발송 결과를 저장한다.
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


# REVIEW_QUEUE 대상은 Slack으로 한 번만 알리고 중복 발송은 notification_log로 막는다.
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


# final_response 단계에서 urgent_alert 라우팅이면 Slack/GitHub 알림을 통합 발송한다.
def dispatch_urgent_alert(state: dict[str, Any]) -> dict[str, Any]:
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
