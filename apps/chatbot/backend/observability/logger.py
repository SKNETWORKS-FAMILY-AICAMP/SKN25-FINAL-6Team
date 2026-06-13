from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


EVENT_ORCHESTRATION_COMPLETED = "orchestration_completed"
EVENT_AGENT_DRAFTED = "agent_drafted"
EVENT_SAFETY_CHECKED = "safety_checked"
EVENT_FINAL_RESPONSE_CREATED = "final_response_created"
EVENT_NODE_STARTED = "node_started"
EVENT_NODE_COMPLETED = "node_completed"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_DB_READ_COMPLETED = "db_read_completed"
EVENT_DB_READ_FAILED = "db_read_failed"
EVENT_DB_WRITE_COMPLETED = "db_write_completed"
EVENT_DB_WRITE_FAILED = "db_write_failed"
EVENT_NOTIFICATION_DISPATCHED = "notification_dispatched"
EVENT_NOTIFICATION_FAILED = "notification_failed"


# admin_event_log/콘솔/LangSmith metadata에서 공통으로 읽을 수 있는 구조화 이벤트를 만든다.
def build_log_event(event_type: str, **payload: Any) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }


# 각 노드와 tool이 동일한 JSON 형태로 실행 결과를 남기도록 하는 경량 logger다.
def log_event(
    event_type: str,
    *,
    ticket_id: int | None = None,
    session_id: str | None = None,
    node_name: str | None = None,
    category: str | None = None,
    routing_target: str | None = None,
    tool_name: str | None = None,
    status: str = "ok",
    error_message: str | None = None,
    error_category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = build_log_event(
        event_type,
        ticket_id=ticket_id,
        session_id=session_id,
        node_name=node_name,
        category=category,
        routing_target=routing_target,
        tool_name=tool_name,
        status=status,
        error_message=error_message,
        error_category=error_category,
        metadata=metadata or {},
    )
    print(json.dumps(event, ensure_ascii=False, default=str))
    return event
