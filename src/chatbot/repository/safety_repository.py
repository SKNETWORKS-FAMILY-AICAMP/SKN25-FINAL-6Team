from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_safety_results(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO safety_results (
                        draft_id,
                        hallucination_score,
                        toxicity_score,
                        policy_violation_score,
                        factuality_score,
                        checked_at,
                        safety_action,
                        safety_reason,
                        retry_count
                    )
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                    RETURNING safety_id
                    """,
                    (
                        payload["draft_id"],
                        payload.get("hallucination_score"),
                        payload.get("toxicity_score"),
                        payload.get("policy_violation_score"),
                        payload.get("factuality_score"),
                        payload.get("safety_action"),
                        payload.get("safety_reason"),
                        payload.get("retry_count", 0),
                    ),
                )
                safety_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "safety_id": safety_id,
            "draft_id": payload["draft_id"],
            "safety_action": payload.get("safety_action"),
        }

    return safe_write(operation="write_safety_results", payload=payload, writer=_write)
