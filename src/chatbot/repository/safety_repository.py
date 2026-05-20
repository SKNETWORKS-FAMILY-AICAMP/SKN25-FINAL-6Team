from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repository.base import safe_write


def save_safety_results(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "draft_id": payload.get("draft_id"),
                "safety_action": payload.get("safety_action"),
                "safety_reason": payload.get("safety_reason"),
                "retry_count": payload.get("retry_count"),
            }
        raise NotImplementedError("DB-backed write_safety_results is not implemented yet.")

    return safe_write(operation="write_safety_results", payload=payload, writer=_write)
