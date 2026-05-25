"""Service orchestration for the weekly dashboard report."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .pdf import render_report_pdf
from .service import build_weekly_report_payload, fetch_weekly_report_data
from .slack import send_weekly_report_pdf
from .state import WeeklyReportState


def _state(state: WeeklyReportState | dict[str, Any]) -> WeeklyReportState:
    return WeeklyReportState.model_validate(state)


def load_data_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    data = fetch_weekly_report_data(current.days)
    return {
        "days": current.days,
        "window_start": data["window"]["window_start"],
        "window_end": data["window"]["window_end"],
        "previous_window_start": data["previous_window"]["window_start"],
        "previous_window_end": data["previous_window"]["window_end"],
        "generated_at": data["generated_at"],
        "dashboard_summary": data["dashboard_summary"],
        "current_rows": data["current_rows"],
        "previous_rows": data["previous_rows"],
    }
def compose_report_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    report = build_weekly_report_payload(
        {
            "window": {
                "days": current.days,
                "window_start": current.window_start,
                "window_end": current.window_end,
            },
            "previous_window": {
                "days": current.days,
                "window_start": current.previous_window_start,
                "window_end": current.previous_window_end,
            },
            "dashboard_summary": current.dashboard_summary,
            "current_rows": current.current_rows,
            "previous_rows": current.previous_rows,
            "generated_at": current.generated_at or datetime.now(),
        }
    )
    return {"report": report}


def render_pdf_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    return {"pdf_bytes": render_report_pdf(current.report)}


def publish_slack_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    channel = (current.slack_channel or "").strip()
    if not channel:
        raise ValueError("slack_channel is required when send_to_slack is enabled")
    filename = f"dashboard_weekly_report_{current.days}d.pdf"
    result = send_weekly_report_pdf(
        pdf_bytes=current.pdf_bytes or b"",
        channel=channel,
        filename=filename,
        title=current.report.get("title") or filename,
        comment=current.slack_comment,
    )
    return {"slack_result": result}


class WeeklyReportWorkflowRunner:
    """Thin compatibility runner that executes the weekly report pipeline in-process."""

    def invoke(self, state: WeeklyReportState | dict[str, Any]) -> dict[str, Any]:
        current = WeeklyReportState.model_validate(state)
        updates = load_data_node(current)
        current = current.model_copy(update=updates)
        updates = compose_report_node(current)
        current = current.model_copy(update=updates)
        updates = render_pdf_node(current)
        current = current.model_copy(update=updates)
        if current.send_to_slack:
            updates = publish_slack_node(current)
            current = current.model_copy(update=updates)
        return current.model_dump()


def build_weekly_report_graph() -> WeeklyReportWorkflowRunner:
    """Build the weekly report workflow runner."""

    return WeeklyReportWorkflowRunner()


def run_weekly_report_workflow(
    days: int = 7,
    *,
    send_to_slack: bool = False,
    slack_channel: str | None = None,
    slack_comment: str | None = None,
) -> dict[str, Any]:
    app = build_weekly_report_graph()
    result = app.invoke(
        WeeklyReportState(
            days=days,
            send_to_slack=send_to_slack,
            slack_channel=slack_channel,
            slack_comment=slack_comment,
        )
    )
    state = WeeklyReportState.model_validate(result)
    payload = {
        "report": state.report,
        "pdf_bytes": state.pdf_bytes,
        "slack_result": state.slack_result,
    }
    return payload
