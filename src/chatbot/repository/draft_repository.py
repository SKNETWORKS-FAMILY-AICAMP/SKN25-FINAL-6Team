from __future__ import annotations

from typing import Any

from chatbot.repository.base import safe_write


def save_answer_draft(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        raise NotImplementedError("DB-backed write_answer_draft is not implemented yet.")

    return safe_write(operation="write_answer_draft", payload=payload, writer=_write)


def save_evidence_docs(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        raise NotImplementedError("DB-backed write_evidence_docs is not implemented yet.")

    return safe_write(operation="write_evidence_docs", payload=payload, writer=_write)
