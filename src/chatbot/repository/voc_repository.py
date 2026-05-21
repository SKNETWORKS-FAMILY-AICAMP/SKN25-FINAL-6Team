from __future__ import annotations

import json
from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_voc_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO voc_feedback (
                        ticket_id,
                        user_id,
                        account_id,
                        voc_type,
                        sentiment,
                        raw_content,
                        topic_keywords,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING voc_id
                    """,
                    (
                        payload["ticket_id"],
                        payload["user_id"],
                        payload.get("account_id"),
                        payload.get("voc_type"),
                        payload.get("sentiment"),
                        payload["raw_content"],
                        json.dumps(payload.get("topic_keywords", []), ensure_ascii=False),
                    ),
                )
                voc_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "voc_id": voc_id,
            "ticket_id": payload["ticket_id"],
            "voc_type": payload.get("voc_type"),
        }

    return safe_write(operation="write_voc_feedback", payload=payload, writer=_write)
