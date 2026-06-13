from __future__ import annotations

from typing import Any


TRACE_METADATA_FIELDS = (
    "ticket_id",
    "session_id",
    "user_id",
    "account_id",
    "ui_category",
    "sub_category",
    "category",
    "routing_target",
    "normalized_query",
    "retrieval_query",
    "retrieval_cache_enabled",
    "retrieval_cache_hit",
    "retrieval_cache_backend",
    "retrieved_count",
    "draft_id",
    "safety_action",
    "safety_passed",
    "factuality_score",
    "hallucination_score",
    "review_required",
)


def build_trace_metadata(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Expose only the operational fields we want to scan in LangSmith."""
    metadata = {
        field: state.get(field)
        for field in TRACE_METADATA_FIELDS
        if state.get(field) is not None
    }

    query = state.get("normalized_query") or state.get("raw_query")
    if query is not None:
        metadata["normalized_query"] = query

    if "retrieved_count" not in metadata:
        metadata["retrieved_count"] = len(state.get("retrieved_documents") or [])

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
