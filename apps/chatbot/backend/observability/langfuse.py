from __future__ import annotations

from typing import Any

from common.observability.langfuse import build_trace_metadata


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


def build_chatbot_trace_metadata(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return build_trace_metadata(state, fields=TRACE_METADATA_FIELDS, **extra)
