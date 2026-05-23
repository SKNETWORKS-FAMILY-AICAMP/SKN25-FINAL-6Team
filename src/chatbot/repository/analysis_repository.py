from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_ticket_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ticket_analysis (
                        ticket_id,
                        category,
                        responder_type,
                        enriched_query,
                        risk_level,
                        sentiment,
                        routing_target,
                        summary,
                        analyzed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING analysis_id
                    """,
                    (
                        payload["ticket_id"],
                        payload.get("category"),
                        payload.get("responder_type") or "AI",
                        payload.get("enriched_query"),
                        payload.get("risk_level"),
                        payload.get("sentiment"),
                        payload.get("routing_target"),
                        payload.get("summary"),
                    ),
                )
                analysis_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "analysis_id": analysis_id,
            "ticket_id": payload["ticket_id"],
            "category": payload.get("category"),
            "routing_target": payload.get("routing_target"),
        }

    return safe_write(operation="write_ticket_analysis", payload=payload, writer=_write)
