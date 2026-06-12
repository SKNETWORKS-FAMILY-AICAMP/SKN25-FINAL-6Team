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
    # now를 고정하면 모든 window 계산이 동일한 기준 시각을 공유해 기간 불일치를 방지한다.
    generated_at = now or datetime.now()

    # 이번 주 window와 직전 동일 기간 window를 계산한다.
    window = get_window(days, now=generated_at)
    previous_window = get_previous_window(window)

    # 7개 KPI + 카테고리별 집계를 각각 이번 주 / 직전 주에 대해 조회한다.
    current_metrics = metrics_query.fetch(window)
    previous_metrics = metrics_query.fetch(previous_window)

    # ticket_analysis + qa_ticket + insight를 조인한 전체 분석 행을 가져온다.
    current_rows = fetch_analysis_rows(window["window_start"], window["window_end"])
    previous_rows = fetch_analysis_rows(previous_window["window_start"], previous_window["window_end"])

    # Nielsen 가중합으로 정렬한 유저 개선 요청 Top 5.
    requests = top_requests_query.fetch(window)
    # Z-Score(시간별) + WoW(일별) + 4주 추세(월별) 폭증 감지.
    alerts = spike_alerts_query.detect(window)

    # AI 액션 생성에는 행 단위 원시 데이터 대신 집계된 수치만 전달해 토큰을 절약한다.
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

    # 위에서 수집한 모든 데이터를 하나의 페이로드 dict로 조립한다.
    # PDF와 Slack 렌더러가 이 dict만 받으면 동작하도록 설계되어 있다.
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

    # send_to_slack=True이면 PDF가 반드시 필요하므로 render_pdf를 자동 활성화한다.
    pdf_bytes: bytes | None = None
    if render_pdf or send_to_slack:
        pdf_bytes = render_report_pdf(report)

    slack_result: dict[str, Any] | None = None
    if send_to_slack:
        if not slack_channel:
            raise ValueError("send_to_slack=True 이면 slack_channel 이 필요합니다")
        # 파일명에 날짜를 포함해 Slack에서 다운로드할 때 기간을 바로 알 수 있게 한다.
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
        "pdf_bytes": pdf_bytes,       # render_pdf=False이면 None
        "slack_result": slack_result,  # send_to_slack=False이면 None
    }
