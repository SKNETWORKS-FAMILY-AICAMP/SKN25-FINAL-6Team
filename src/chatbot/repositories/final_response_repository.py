from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repositories.base import safe_write


def save_final_response(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            response_id = 9000 + (payload.get("ticket_id") or 0)
            return {
                "status": "ok",
                "response_id": response_id,
                "ticket_id": payload.get("ticket_id"),
                "draft_id": payload.get("draft_id"),
                "safety_action": payload.get("safety_action"),
                "stored": True,
            }
        raise NotImplementedError("DB-backed write_final_response is not implemented yet.")

    return safe_write(operation="write_final_response", payload=payload, writer=_write)
