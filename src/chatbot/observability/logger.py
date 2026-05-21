from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


EVENT_ORCHESTRATION_COMPLETED = "orchestration_completed"
EVENT_AGENT_DRAFTED = "agent_drafted"
EVENT_SAFETY_CHECKED = "safety_checked"
EVENT_FINAL_RESPONSE_CREATED = "final_response_created"
EVENT_DB_READ_COMPLETED = "db_read_completed"
EVENT_DB_READ_FAILED = "db_read_failed"
EVENT_DB_WRITE_COMPLETED = "db_write_completed"
EVENT_DB_WRITE_FAILED = "db_write_failed"
EVENT_NOTIFICATION_DISPATCHED = "notification_dispatched"
EVENT_NOTIFICATION_FAILED = "notification_failed"


def get_log_mode() -> str:
    mode = os.getenv("CHATBOT_LOG_MODE", "both").strip().lower()
    if mode not in {"summary", "raw", "both", "none"}:
        return "both"
    return mode


def build_log_event(event_type: str, **payload: Any) -> dict[str, Any]:
    """Build a structured admin log event without binding to a logging backend yet."""
    return {
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }


def log_event(
    event_type: str,
    *,
    ticket_id: int | None = None,
    session_id: str | None = None,
    node_name: str | None = None,
    category: str | None = None,
    routing_target: str | None = None,
    classification_method: str | None = None,
    tool_name: str | None = None,
    status: str = "ok",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Print a structured admin log event as JSON and return it for tests."""
    event = build_log_event(
        event_type,
        ticket_id=ticket_id,
        session_id=session_id,
        node_name=node_name,
        category=category,
        routing_target=routing_target,
        classification_method=classification_method,
        tool_name=tool_name,
        status=status,
        error_message=error_message,
        metadata=metadata or {},
    )
    if get_log_mode() in {"raw", "both"}:
        print(json.dumps(event, ensure_ascii=False, default=str))
    return event


def _shorten(text: str | None, limit: int = 320) -> str:
    if not text:
        return "-"
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def log_operator_summary(
    *,
    ticket_id: int | None,
    session_id: str | None,
    user_id: str | None,
    raw_query: str | None,
    category: str | None,
    routing_target: str | None,
    safety_action: str | None,
    final_text: str | None,
    notification_result: dict[str, Any] | None = None,
) -> None:
    """Print one human-readable summary after a chatbot turn finishes."""
    if get_log_mode() not in {"summary", "both"}:
        return

    notification_status = "-"
    if notification_result:
        notification_status = str(notification_result.get("status") or "-")
        reason = notification_result.get("reason")
        if reason:
            notification_status = f"{notification_status} ({reason})"

    lines = [
        "",
        "=" * 60,
        "[CS 문의 처리 요약]",
        f"ticket_id          : {ticket_id if ticket_id is not None else '-'}",
        f"session_id         : {session_id or '-'}",
        f"user_id            : {user_id or '-'}",
        f"category           : {category or '-'}",
        f"routing_target     : {routing_target or '-'}",
        f"safety_action      : {safety_action or '-'}",
        f"notification       : {notification_status}",
        "",
        "[문의]",
        _shorten(raw_query, limit=500),
        "",
        "[최종 응답]",
        _shorten(final_text, limit=700),
        "=" * 60,
    ]
    print("\n".join(lines))
