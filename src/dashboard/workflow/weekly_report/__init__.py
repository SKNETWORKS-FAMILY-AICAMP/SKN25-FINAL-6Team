"""Weekly report helpers for dashboard operations."""

from __future__ import annotations

from typing import Any

from .errors import SlackReportError
from .service import (
    WeeklyReportService,
    build_weekly_report_payload,
    fetch_weekly_report_data,
    run_weekly_report_workflow,
)


def render_report_pdf(*args: Any, **kwargs: Any) -> bytes:
    from .pdf import render_report_pdf as _render_report_pdf

    return _render_report_pdf(*args, **kwargs)


def send_weekly_report_pdf(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .slack import send_weekly_report_pdf as _send_weekly_report_pdf

    return _send_weekly_report_pdf(*args, **kwargs)


__all__ = [
    "WeeklyReportService",
    "run_weekly_report_workflow",
    "fetch_weekly_report_data",
    "build_weekly_report_payload",
    "SlackReportError",
    "render_report_pdf",
    "send_weekly_report_pdf",
]
