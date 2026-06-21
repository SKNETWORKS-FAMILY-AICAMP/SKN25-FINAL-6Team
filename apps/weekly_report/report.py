"""Weekly report orchestration entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import db.metrics as metrics_query
import db.spike_alerts as spike_alerts_query
import db.top_requests as top_requests_query
from ai.actions import generate_ai_actions, is_fallback_ai_actions
from build.distributions import distribution
from build.payload import build_report_payload
from common.observability.langfuse import observe_if_enabled, record_current_scores
from db.analysis import fetch_analysis_rows
from observability.langfuse import link_weekly_report_trace
from output.pdf import render_report_pdf
from output.slack import send_weekly_report_pdf
from utils.date_range import get_previous_window, get_window


@observe_if_enabled(
    name="weekly_report_run",
    as_type="chain",
    tags=["weekly-report", "feature:report-build"],
)
def run(
    days: int = 7,
    *,
    render_pdf: bool = False,
    send_to_slack: bool = False,
    slack_channel: str | None = None,
    slack_comment: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now()
    link_weekly_report_trace(
        {},
        tags=["weekly-report", "feature:report-build"],
        input_payload={"days": days, "render_pdf": render_pdf, "send_to_slack": send_to_slack},
        days=days,
        render_pdf=render_pdf,
        send_to_slack=send_to_slack,
        channel=slack_channel,
    )

    window = get_window(days, now=generated_at)
    previous_window = get_previous_window(window)

    current_metrics = metrics_query.fetch(window)
    previous_metrics = metrics_query.fetch(previous_window)
    current_rows = fetch_analysis_rows(window["window_start"], window["window_end"])
    previous_rows = fetch_analysis_rows(previous_window["window_start"], previous_window["window_end"])
    requests = top_requests_query.fetch(window)
    alerts = spike_alerts_query.detect(window)

    ai_input = {
        "summary": {
            "total_count": len(current_rows),
            "prev_total": len(previous_rows),
        },
        "spike_alerts": alerts,
        "top5_improvements": requests,
        "category_distribution": distribution(current_rows, "category"),
    }
    ai_interp = generate_ai_actions(ai_input)

    report = build_report_payload(
        window=window,
        previous_window=previous_window,
        current_metrics=current_metrics,
        previous_metrics=previous_metrics,
        current_rows=current_rows,
        previous_rows=previous_rows,
        requests=requests,
        alerts=alerts,
        ai_interp=ai_interp,
        generated_at=generated_at,
    )

    if send_to_slack and not slack_channel:
        raise ValueError("send_to_slack=True requires slack_channel.")

    pdf_bytes: bytes | None = None
    if render_pdf or send_to_slack:
        pdf_bytes = render_report_pdf(report)

    slack_result: dict[str, Any] | None = None
    if send_to_slack:
        filename = f"weekly_report_{days}d_{generated_at.date().isoformat()}.pdf"
        slack_result = send_weekly_report_pdf(
            pdf_bytes=pdf_bytes or b"",
            channel=slack_channel,
            filename=filename,
            title=report["title"],
            comment=slack_comment,
        )

    result = {
        "report": report,
        "pdf_bytes": pdf_bytes,
        "slack_result": slack_result,
    }
    record_current_scores(
        {
            "report_generated": True,
            "pdf_rendered": pdf_bytes is not None,
            "slack_delivered": slack_result is not None,
            "ai_fallback_used": is_fallback_ai_actions(ai_interp),
        },
        comments={
            "slack_delivered": slack_channel or "",
            "ai_fallback_used": str(ai_interp.get("headline") or ""),
        },
    )
    link_weekly_report_trace(
        report,
        tags=["weekly-report", "feature:report-build", "feature:report-delivery"],
        output_payload={
            "requests_count": len(requests),
            "alerts_count": sum(len(alerts.get(key, [])) for key in ("hourly", "daily", "monthly")),
            "slack_sent": slack_result is not None,
            "pdf_rendered": pdf_bytes is not None,
        },
        requests_count=len(requests),
        alerts_count=sum(len(alerts.get(key, [])) for key in ("hourly", "daily", "monthly")),
        current_rows_count=len(current_rows),
        previous_rows_count=len(previous_rows),
        slack_sent=slack_result is not None,
        pdf_rendered=pdf_bytes is not None,
    )
    return result
