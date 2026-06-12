from __future__ import annotations

import json
import os
from typing import Any
from urllib import request
from urllib.error import HTTPError

from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_NOTIFICATION_DISPATCHED, EVENT_NOTIFICATION_FAILED, log_event
from chatbot.repository.notification_repository import notification_log_exists, save_notification_log


GITHUB_API_BASE_URL = "https://api.github.com"
BUG_CATEGORY_VALUES = {"bug", "버그", "인게임 버그", "오류"}


def _inquiry_content(state: dict[str, Any]) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "").strip()


def _is_in_game_bug_alert(state: dict[str, Any]) -> bool:
    # 긴급 알림은 urgent_alert로 라우팅된 버그성 문의에만 생성한다.
    return (
        state.get("routing_target") == "urgent_alert"
        and (
            state.get("reasoning_node") == "bug_agent"
            or str(state.get("category") or "").strip().lower() in BUG_CATEGORY_VALUES
        )
    )


def _github_labels() -> list[str]:
    raw_labels = os.getenv("GITHUB_ISSUE_LABELS", "bug,in-game,chatbot")
    return [label.strip() for label in raw_labels.split(",") if label.strip()]


def _github_issue_title(state: dict[str, Any]) -> str:
    content = _inquiry_content(state)
    if len(content) > 60:
        content = f"{content[:57]}..."
    return f"[인게임 버그] {content or '운영자 확인 필요'}"


def _github_issue_body(state: dict[str, Any]) -> str:
    # 운영자가 GitHub issue만 보고도 티켓과 답변 상태를 추적할 수 있게 핵심 상태만 담는다.
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
        f"{_inquiry_content(state)}\n\n"
        "## Final Response\n"
        f"{state.get('final_text') or ''}\n"
    )


def _create_github_issue(title: str, body: str) -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not token:
        return {"status": "mock", "reason": "github token is not configured", "message": body}
    if not repository:
        return {"status": "mock", "reason": "github repository is not configured", "message": body}

    try:
        payload = {
            "title": title,
            "body": body,
            "labels": _github_labels(),
        }
        req = request.Request(
            f"{GITHUB_API_BASE_URL}/repos/{repository}/issues",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "skn25-chatbot",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API HTTP {exc.code}: {response_body}") from exc

        data = json.loads(response_body)
        return {
            "status": "ok",
            "issue_number": str(data.get("number", "")),
            "issue_url": str(data.get("html_url", "")),
        }
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_NOTIFICATION_FAILED,
            tool_name="github_issue",
            status="error",
            error_message=str(exc),
            error_category=error_category,
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": str(exc),
        }


def _dispatch_github_issue_for_bug(state: dict[str, Any]) -> dict[str, Any]:
    if not _is_in_game_bug_alert(state):
        return {"status": "skipped", "reason": "not an in-game urgent bug alert"}

    existing_log = notification_log_exists(state.get("ticket_id"), "github_issue")
    if existing_log.get("exists"):
        return {"status": "skipped", "reason": "github issue already created for ticket_id"}

    title = _github_issue_title(state)
    body = _github_issue_body(state)
    result = _create_github_issue(title, body)
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


def dispatch_urgent_alert(state: dict[str, Any]) -> dict[str, Any]:
    # final_response 단계에서 호출되며, 대상이 아니면 skipped로 남겨 흐름을 단순하게 유지한다.
    if state.get("routing_target") != "urgent_alert":
        return {"status": "skipped", "reason": "routing_target is not urgent_alert"}

    github_issue_result = _dispatch_github_issue_for_bug(state)
    log_event(
        EVENT_NOTIFICATION_DISPATCHED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="final_response",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status=github_issue_result.get("status", "unknown"),
        error_category=github_issue_result.get("error_category"),
        metadata={
            "channel": "github_issue",
            "result": github_issue_result,
        },
    )
    return github_issue_result
