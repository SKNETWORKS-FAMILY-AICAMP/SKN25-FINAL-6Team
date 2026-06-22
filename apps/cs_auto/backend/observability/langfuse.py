from __future__ import annotations

from typing import Any

from common.observability.langfuse import build_trace_metadata, build_trace_tags, link_current_trace


CS_AUTO_TRACE_METADATA_FIELDS = (
    "ticket_id",
    "draft_id",
    "response_id",
    "analysis_id",
    "admin_id",
    "user_id",
    "account_id",
    "session_id",
    "login_id",
    "email",
    "category",
    "routing_target",
    "risk_level",
    "sentiment",
    "safety_action",
    "retry_count",
    "status",
    "source_type",
    "message",
)


def build_cs_auto_trace_metadata(payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return build_trace_metadata(payload, fields=CS_AUTO_TRACE_METADATA_FIELDS, **extra)


def link_cs_auto_trace(
    payload: dict[str, Any],
    *,
    user_id: str | int | None = None,
    session_id: str | int | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    input_payload: Any | None = None,
    output_payload: Any | None = None,
    metadata_source: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    source = metadata_source or payload
    resolved_user_id = user_id
    if resolved_user_id is None:
        resolved_user_id = payload.get("user_id") or payload.get("admin_id") or payload.get("login_id")
    resolved_session_id = session_id
    if resolved_session_id is None:
        resolved_session_id = payload.get("session_id") or payload.get("ticket_id")

    link_current_trace(
        user_id=resolved_user_id,
        session_id=resolved_session_id,
        tags=build_trace_tags("cs-auto", *(tags or [])),
        metadata=build_cs_auto_trace_metadata(source, **extra),
        input_payload=input_payload,
        output_payload=output_payload,
    )
