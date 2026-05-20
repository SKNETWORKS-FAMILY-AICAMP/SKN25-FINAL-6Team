from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repository.base import safe_write


def save_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "ticket_id": payload.get("ticket_id", 1001),
                "session_id": payload.get("session_id"),
                "raw_query": payload.get("raw_query"),
            }
        raise NotImplementedError("DB-backed write_qa_ticket is not implemented yet.")

    return safe_write(operation="write_qa_ticket", payload=payload, writer=_write)
