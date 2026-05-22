"""LangGraph orchestration for the weekly dashboard report."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph

from .pdf import render_report_pdf
from .service import build_weekly_report_payload, fetch_weekly_report_data
from .slack import send_weekly_report_pdf
from .state import WeeklyReportState


Route = Literal["publish", "stop"]


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


def _compose_report_from_state(payload: dict[str, Any]) -> dict[str, Any]:
    return build_weekly_report_payload(
        {
            "window": {
                "days": payload["days"],
                "window_start": payload["window_start"],
                "window_end": payload["window_end"],
            },
            "previous_window": {
                "days": payload["days"],
                "window_start": payload["previous_window_start"],
                "window_end": payload["previous_window_end"],
            },
            "dashboard_summary": payload["dashboard_summary"],
            "current_rows": payload["current_rows"],
            "previous_rows": payload["previous_rows"],
            "generated_at": payload.get("generated_at") or datetime.now(),
        }
    )


REPORT_COMPUTE_CHAIN = RunnableLambda(_compose_report_from_state)


def compose_report_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    report = REPORT_COMPUTE_CHAIN.invoke(current.model_dump())
    return {"report": report}


def render_pdf_node(state: WeeklyReportState) -> dict[str, Any]:
    current = _state(state)
    return {"pdf_bytes": render_report_pdf(current.report)}


def route_after_pdf(state: WeeklyReportState) -> Route:
    current = _state(state)
    return cast(Route, "publish" if current.send_to_slack else "stop")


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


def build_weekly_report_graph():
    graph = StateGraph(WeeklyReportState)
    graph.add_node("load_data", load_data_node)
    graph.add_node("compose_report", compose_report_node)
    graph.add_node("render_pdf", render_pdf_node)
    graph.add_node("publish_slack", publish_slack_node)

    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "compose_report")
    graph.add_edge("compose_report", "render_pdf")
    graph.add_conditional_edges("render_pdf", route_after_pdf, {"publish": "publish_slack", "stop": END})
    graph.add_edge("publish_slack", END)
    return graph.compile()


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
