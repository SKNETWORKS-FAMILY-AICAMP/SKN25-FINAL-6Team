from __future__ import annotations

from typing import Any

from config import settings

from chatbot.repositories.base import safe_write


def save_safety_results(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        if settings.use_seed_payload:
            return {
                "status": "ok",
                "draft_id": payload.get("draft_id"),
                "decision_type": payload.get("decision_type"),
            }
        raise NotImplementedError("DB-backed write_safety_results is not implemented yet.")

    return safe_write(operation="write_safety_results", payload=payload, writer=_write)
