from __future__ import annotations

from typing import Any

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_write


def save_answer_draft(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO answer_draft (
                        ticket_id,
                        analysis_id,
                        draft_text,
                        prompt_version,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING draft_id
                    """,
                    (
                        payload["ticket_id"],
                        payload["analysis_id"],
                        payload.get("draft_text"),
                        payload.get("prompt_version") or "chatbot-db-v1",
                    ),
                )
                draft_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "draft_id": draft_id,
            "ticket_id": payload["ticket_id"],
            "analysis_id": payload["analysis_id"],
        }

    return safe_write(operation="write_answer_draft", payload=payload, writer=_write)


def save_evidence_docs(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evidence_docs (
                        draft_id,
                        source_type,
                        source_id,
                        evidence_text,
                        relevance_score,
                        retrieval_rank
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING evidence_id
                    """,
                    (
                        payload["draft_id"],
                        payload.get("source_type"),
                        payload.get("source_id"),
                        payload.get("evidence_text"),
                        payload.get("relevance_score"),
                        payload.get("retrieval_rank"),
                    ),
                )
                evidence_id = cur.fetchone()[0]
        return {
            "status": "ok",
            "stored": True,
            "evidence_id": evidence_id,
            "draft_id": payload["draft_id"],
            "source_type": payload.get("source_type"),
            "source_id": payload.get("source_id"),
        }

    return safe_write(operation="write_evidence_docs", payload=payload, writer=_write)
