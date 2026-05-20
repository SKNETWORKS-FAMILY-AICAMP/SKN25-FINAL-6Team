from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repository.base import safe_write


def save_failed_query(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "ticket_id": payload.get("ticket_id"),
                "query": payload.get("query"),
                "category": payload.get("category"),
                "reason": payload.get("reason"),
            }
        raise NotImplementedError("DB-backed write_failed_query is not implemented yet.")

    return safe_write(operation="write_failed_query", payload=payload, writer=_write)
