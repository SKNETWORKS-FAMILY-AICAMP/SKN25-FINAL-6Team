from __future__ import annotations

from typing import Any


TRACE_METADATA_FIELDS = (
    "ticket_id",
    "session_id",
    "user_id",
    "account_id",
    "category",
    "routing_target",
    "analysis_id",
    "draft_id",
)


def build_trace_metadata(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    metadata = {
        field: state.get(field)
        for field in TRACE_METADATA_FIELDS
        if state.get(field) is not None
    }
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def build_runnable_config(state: dict[str, Any], *, run_name: str) -> dict[str, Any]:
    ticket_id = state.get("ticket_id")
    session_id = state.get("session_id")
    return {
        "run_name": run_name,
        "tags": ["chatbot", f"ticket:{ticket_id}", f"session:{session_id}"],
        "metadata": build_trace_metadata(state),
    }
