from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_final_response(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO final_response (
                        ticket_id,
                        draft_id,
                        final_text,
                        safety_action,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING response_id
                    """,
                    (
                        payload["ticket_id"],
                        payload.get("draft_id"),
                        payload["final_text"],
                        payload.get("safety_action"),
                    ),
                )
                response_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "response_id": response_id,
            "ticket_id": payload["ticket_id"],
            "draft_id": payload.get("draft_id"),
            "safety_action": payload.get("safety_action"),
        }

    return safe_write(operation="write_final_response", payload=payload, writer=_write)
