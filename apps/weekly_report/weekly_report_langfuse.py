from __future__ import annotations

from typing import Any

from common.observability.langfuse import build_trace_metadata, build_trace_tags, link_current_trace


WEEKLY_REPORT_TRACE_METADATA_FIELDS = (
    "days",
    "window_start",
    "window_end",
    "requests_count",
    "alerts_count",
    "current_rows_count",
    "previous_rows_count",
    "review_rows_count",
    "analysis_count",
    "hourly_alert_count",
    "daily_alert_count",
    "monthly_trend_count",
    "top_requests_count",
    "slack_sent",
    "pdf_rendered",
    "render_pdf",
    "send_to_slack",
    "channel",
    "filename",
    "title",
    "status",
)


def build_weekly_report_trace_metadata(payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return build_trace_metadata(payload, fields=WEEKLY_REPORT_TRACE_METADATA_FIELDS, **extra)


def _resolve_session_id(payload: dict[str, Any]) -> str | None:
    if payload.get("session_id") is not None:
        return str(payload["session_id"])
    if payload.get("window_end") is not None:
        return str(payload["window_end"])
    if isinstance(payload.get("window"), dict) and payload["window"].get("window_end") is not None:
        return str(payload["window"]["window_end"])
    if payload.get("generated_at") is not None:
        return str(payload["generated_at"])
    return None


def link_weekly_report_trace(
    payload: dict[str, Any],
    *,
    tags: list[str] | tuple[str, ...] | None = None,
    input_payload: Any | None = None,
    output_payload: Any | None = None,
    metadata_source: dict[str, Any] | None = None,
    session_id: str | int | None = None,
    **extra: Any,
) -> None:
    source = metadata_source or payload
    resolved_session_id = None if session_id is None else str(session_id)
    if resolved_session_id is None:
        resolved_session_id = _resolve_session_id(payload)

    link_current_trace(
        session_id=resolved_session_id,
        tags=build_trace_tags("weekly-report", *(tags or [])),
        metadata=build_weekly_report_trace_metadata(source, **extra),
        input_payload=input_payload,
        output_payload=output_payload,
    )
