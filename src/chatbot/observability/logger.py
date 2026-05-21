from __future__ import annotations

import json
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
    print(json.dumps(event, ensure_ascii=False, default=str))
    return event
