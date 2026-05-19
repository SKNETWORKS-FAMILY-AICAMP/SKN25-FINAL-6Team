from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repositories.base import safe_write


def save_ticket_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "analysis_id": payload.get("analysis_id"),
                "ticket_id": payload.get("ticket_id"),
                "category": payload.get("category"),
                "routing_target": payload.get("routing_target"),
                "summary": payload.get("summary"),
            }
        raise NotImplementedError("DB-backed write_ticket_analysis is not implemented yet.")

    return safe_write(operation="write_ticket_analysis", payload=payload, writer=_write)
