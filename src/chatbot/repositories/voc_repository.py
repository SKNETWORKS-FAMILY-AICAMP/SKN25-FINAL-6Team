from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repositories.base import safe_write


def save_voc_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "ticket_id": payload.get("ticket_id"),
                "voc_type": payload.get("voc_type"),
                "topic_keywords": payload.get("topic_keywords", []),
                "stored": True,
            }
        raise NotImplementedError("DB-backed write_voc_feedback is not implemented yet.")

    return safe_write(operation="write_voc_feedback", payload=payload, writer=_write)
