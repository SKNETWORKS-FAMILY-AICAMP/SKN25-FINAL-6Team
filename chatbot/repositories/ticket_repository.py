from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repositories.base import safe_write


def save_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {"status": "ok", "ticket_id": payload.get("ticket_id", 1001)}
        raise NotImplementedError("DB-backed write_qa_ticket is not implemented yet.")

    return safe_write(operation="write_qa_ticket", payload=payload, writer=_write)


def append_qa_message(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "ticket_id": payload.get("ticket_id"),
                "role": payload.get("role"),
                "appended": True,
            }
        raise NotImplementedError("DB-backed append_qa_ticket_message is not implemented yet.")

    return safe_write(operation="append_qa_ticket_message", payload=payload, writer=_write)
