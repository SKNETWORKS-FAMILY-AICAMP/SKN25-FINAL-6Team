from __future__ import annotations

from typing import Any

from common.observability.langfuse import build_trace_metadata, build_trace_tags, link_current_trace


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

LOGIN_TRACE_METADATA_FIELDS = (
    "login_success",
    "user_id",
    "account_id",
    "game_id",
    "email",
    "server_region",
)


def build_chatbot_trace_metadata(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return build_trace_metadata(state, fields=TRACE_METADATA_FIELDS, **extra)


def build_login_trace_metadata(payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return build_trace_metadata(payload, fields=LOGIN_TRACE_METADATA_FIELDS, **extra)


def link_chatbot_trace(
    state: dict[str, Any],
    *,
    tags: list[str] | tuple[str, ...] | None = None,
    input_payload: Any | None = None,
    output_payload: Any | None = None,
    metadata_source: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    payload = metadata_source or state
    link_current_trace(
        user_id=state.get("user_id"),
        session_id=state.get("session_id"),
        tags=build_trace_tags("chatbot", *(tags or [])),
        metadata=build_chatbot_trace_metadata(payload, **extra),
        input_payload=input_payload,
        output_payload=output_payload,
    )
