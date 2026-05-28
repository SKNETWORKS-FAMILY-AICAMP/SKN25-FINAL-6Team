from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_notification_log(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notification_logs (
                        ticket_id,
                        channel,
                        status,
                        message,
                        error_message,
                        error_category,
                        sent_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING notification_id
                    """,
                    (
                        payload["ticket_id"],
                        payload.get("channel") or "slack",
                        payload.get("status"),
                        payload.get("message"),
                        payload.get("error_message"),
                        payload.get("error_category"),
                    ),
                )
                notification_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "notification_id": notification_id,
            "ticket_id": payload["ticket_id"],
            "channel": payload.get("channel") or "slack",
        }

    return safe_write(operation="write_notification_log", payload=payload, writer=_write)
