from __future__ import annotations

from typing import Any

from chatbot.repository.base import safe_write


def save_voc_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        raise NotImplementedError("DB-backed write_voc_feedback is not implemented yet.")

    return safe_write(operation="write_voc_feedback", payload=payload, writer=_write)
