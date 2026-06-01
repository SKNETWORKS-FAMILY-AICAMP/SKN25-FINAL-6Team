from __future__ import annotations

from typing import Any


def append_user_turn(history: list[dict[str, Any]] | None, content: str) -> list[dict[str, Any]]:
    """Return a new in-memory history with one user turn appended."""
    next_history = list(history or [])
    next_history.append({"role": "user", "content": content})
    return next_history


def append_assistant_turn(history: list[dict[str, Any]] | None, content: str) -> list[dict[str, Any]]:
    """Return a new in-memory history with one assistant turn appended."""
    next_history = list(history or [])
    next_history.append({"role": "assistant", "content": content})
    return next_history

