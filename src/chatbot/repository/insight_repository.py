from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_insight(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO insight (
                        user_id,
                        ticket_id,
                        account_id,
                        content_summary,
                        category,
                        sentiment,
                        risk_level,
                        pattern_risk_level,
                        inquiry_created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING insight_id
                    """,
                    (
                        payload["user_id"],
                        payload["ticket_id"],
                        payload.get("account_id"),
                        payload.get("content_summary"),
                        payload.get("category"),
                        payload.get("sentiment"),
                        payload.get("risk_level"),
                        payload.get("pattern_risk_level"),
                    ),
                )
                insight_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "insight_id": insight_id,
            "ticket_id": payload["ticket_id"],
        }

    return safe_write(operation="write_insight", payload=payload, writer=_write)
