from __future__ import annotations

from typing import Any

from chatbot.repository.base import safe_write


def save_failed_query(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        raise NotImplementedError("DB-backed write_failed_query is not implemented yet.")

    return safe_write(operation="write_failed_query", payload=payload, writer=_write)
