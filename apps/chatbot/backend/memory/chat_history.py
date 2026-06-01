from __future__ import annotations

from typing import Any

DEFAULT_MAX_HISTORY_TURNS = 3


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


def trim_recent_turns(
    history: list[dict[str, Any]] | None,
    *,
    max_turns: int = DEFAULT_MAX_HISTORY_TURNS,
) -> list[dict[str, Any]]:
    """Return only the most recent user turns and their following messages."""
    if max_turns <= 0:
        return []

    messages = list(history or [])
    user_turns_seen = 0
    start_index = 0

    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") != "user":
            continue
        user_turns_seen += 1
        if user_turns_seen == max_turns:
            start_index = index
            break

    return messages[start_index:]


def build_compact_history(
    history: list[dict[str, Any]] | None,
    *,
    conversation_summary: str | None = None,
    max_turns: int = DEFAULT_MAX_HISTORY_TURNS,
) -> list[dict[str, Any]]:
    """Combine an optional summary with the recent-turn chat history."""
    compact_history = trim_recent_turns(history, max_turns=max_turns)
    summary = (conversation_summary or "").strip()
    if not summary:
        return compact_history
    return [
        {
            "role": "system",
            "content": f"Conversation summary:\n{summary}",
        },
        *compact_history,
    ]

