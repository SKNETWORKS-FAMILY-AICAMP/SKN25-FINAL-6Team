from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repository.base import safe_write


def save_answer_draft(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            draft_id = 5000 + (payload.get("ticket_id") or 0)
            return {
                "status": "ok",
                "draft_id": draft_id,
                "ticket_id": payload.get("ticket_id"),
                "analysis_id": payload.get("analysis_id"),
                "draft_text": payload.get("draft_text"),
                "prompt_version": payload.get("prompt_version"),
            }
        raise NotImplementedError("DB-backed write_answer_draft is not implemented yet.")

    return safe_write(operation="write_answer_draft", payload=payload, writer=_write)


def save_evidence_docs(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "draft_id": payload.get("draft_id"),
                "source_type": payload.get("source_type"),
                "source_id": payload.get("source_id"),
                "retrieval_rank": payload.get("retrieval_rank"),
            }
        raise NotImplementedError("DB-backed write_evidence_docs is not implemented yet.")

    return safe_write(operation="write_evidence_docs", payload=payload, writer=_write)
