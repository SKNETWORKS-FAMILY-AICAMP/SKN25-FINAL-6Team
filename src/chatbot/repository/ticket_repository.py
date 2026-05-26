from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def save_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO qa_ticket (
                        ticket_id,
                        user_id,
                        account_id,
                        title,
                        raw_query,
                        source_type,
                        status,
                        inquiry_created_at,
                        session_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (ticket_id)
                    DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        account_id = EXCLUDED.account_id,
                        title = EXCLUDED.title,
                        raw_query = EXCLUDED.raw_query,
                        source_type = EXCLUDED.source_type,
                        status = EXCLUDED.status,
                        session_id = EXCLUDED.session_id
                    """,
                    (
                        _optional_int(payload["ticket_id"]),
                        _optional_int(payload["user_id"]),
                        _optional_int(payload.get("account_id")),
                        payload.get("title") or "chatbot inquiry",
                        payload["raw_query"],
                        payload.get("source_type") or "chatbot",
                        payload.get("status") or "open",
                        _optional_int(payload.get("session_id")),
                    ),
                )
        return {
            "status": "ok",
            "stored": True,
            "ticket_id": payload["ticket_id"],
        }

    return safe_write(operation="write_qa_ticket", payload=payload, writer=_write)
