from __future__ import annotations

import json
from typing import Any

from common.db.connection import db_connection


# 로그 payload의 id 값을 DB 저장 가능한 int/None으로 정리한다.
def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# 노드 실행/도구 호출/에러 같은 운영 이벤트를 admin_event_log에 저장한다.
def save_admin_event_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an admin event without using safe_write to avoid log recursion."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_event_logs (
                        ticket_id,
                        session_id,
                        node_name,
                        event_type,
                        category,
                        routing_target,
                        tool_name,
                        status,
                        error_message,
                        error_category,
                        metadata,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING log_id
                    """,
                    (
                        _optional_int(payload.get("ticket_id")),
                        _optional_int(payload.get("session_id")),
                        payload.get("node_name"),
                        payload.get("event_type"),
                        payload.get("category"),
                        payload.get("routing_target"),
                        payload.get("tool_name"),
                        payload.get("status"),
                        payload.get("error_message"),
                        payload.get("error_category"),
                        json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                    ),
                )
                log_id = cur.fetchone()[0]
        return {"status": "ok", "stored": True, "log_id": log_id}
    except Exception as exc:
        return {
            "status": "error",
            "stored": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }
