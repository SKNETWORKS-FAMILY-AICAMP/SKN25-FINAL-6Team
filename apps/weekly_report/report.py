"""주간 운영 리포트 진입점.

Airflow DAG 또는 직접 실행에서 이 모듈을 호출한다.

흐름:
    window    = utils.date_range.get_window(days=7)
    metrics   = db.metrics.fetch(window)
    requests  = db.top_requests.fetch(window)
    alerts    = db.spike_alerts.detect(window)
    ai_interp = ai.actions.generate_ai_actions(...)
    report    = build.payload.build_report_payload(...)
    pdf_bytes = output.pdf.render_report_pdf(report)
    slack.send(pdf_bytes, channel="#ops")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import db.metrics as metrics_query
import db.top_requests as top_requests_query
import db.spike_alerts as spike_alerts_query
from db.analysis import fetch_analysis_rows
from ai.actions import generate_ai_actions
from build.distributions import distribution
from build.payload import build_report_payload
from output.pdf import render_report_pdf
from output.slack import send_weekly_report_pdf
from utils.date_range import get_window, get_previous_window


def run(
    days: int = 7,
    *,
    render_pdf: bool = False,
    send_to_slack: bool = False,
    slack_channel: str | None = None,
    slack_comment: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """주간 리포트 전체 파이프라인을 실행한다.

    Args:
        days: 조회 기간(일). 기본 7일.
        render_pdf: True 이면 PDF 바이트를 생성해 반환값에 포함한다.
        send_to_slack: True 이면 PDF를 Slack에 전송한다. render_pdf도 자동 활성화된다.
        slack_channel: Slack 채널 이름 또는 채널 ID.
        slack_comment: Slack 메시지 본문.
        now: 기준 시각 (테스트용). None 이면 현재 시각 사용.

    Returns:
        {"report": dict, "pdf_bytes": bytes | None, "slack_result": dict | None}
    """
    generated_at = now or datetime.now()

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

    pdf_bytes: bytes | None = None
    if render_pdf or send_to_slack:
        pdf_bytes = render_report_pdf(report)

    slack_result: dict[str, Any] | None = None
    if send_to_slack:
        if not slack_channel:
            raise ValueError("send_to_slack=True 이면 slack_channel 이 필요합니다")
        filename = f"weekly_report_{days}d_{generated_at.date().isoformat()}.pdf"
        slack_result = send_weekly_report_pdf(
            pdf_bytes=pdf_bytes or b"",
            channel=slack_channel,
            filename=filename,
            title=report["title"],
            comment=slack_comment,
        )

    return {
        "report": report,
        "pdf_bytes": pdf_bytes,
        "slack_result": slack_result,
    }
