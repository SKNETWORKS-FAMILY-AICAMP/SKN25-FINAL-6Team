from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_failed_query(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO failed_queries (
                        ticket_id,
                        query,
                        category,
                        reason,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING failed_query_id
                    """,
                    (
                        payload["ticket_id"],
                        payload["query"],
                        payload.get("category"),
                        payload.get("reason"),
                    ),
                )
                failed_query_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "failed_query_id": failed_query_id,
            "ticket_id": payload["ticket_id"],
            "category": payload.get("category"),
        }

    return safe_write(operation="write_failed_query", payload=payload, writer=_write)
