"""주간 운영 리포트 진입점.

Airflow DAG 또는 직접 실행에서 이 모듈을 호출한다.

흐름:
    window    = date_range.get_window(days=7)
    metrics   = weekly_metrics.fetch(window)
    requests  = top_requests.fetch(window)
    alerts    = spike_alerts.detect(window)
    summary   = ai_summary.generate(metrics, requests, alerts)
    pdf_bytes = pdf.render(window, metrics, ...)
    slack.send(pdf_bytes, channel="#ops")
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from textwrap import shorten
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from db import _fetch_all

import ai_summary
import date_range
import pdf as pdf_module
import slack as slack_module
import spike_alerts
import top_requests
import weekly_metrics
from util import generate_review_row_interpretations, rate, safe_average


# ──────────────────────────────────────────────────────────────────────────────
# 분석 행 쿼리 (기존 workflow/weekly_report/service.py 의 _fetch_analysis_rows 이동)
# ──────────────────────────────────────────────────────────────────────────────

def _latest_insight_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                i.insight_id,
                i.content_summary,
                i.category AS insight_category,
                i.sentiment AS insight_sentiment,
                i.risk_level AS insight_risk_level,
                i.pattern_risk_level,
                i.inquiry_created_at AS insight_created_at
            FROM insight i
            WHERE i.ticket_id = t.ticket_id
            ORDER BY i.inquiry_created_at DESC NULLS LAST, i.insight_id DESC
            LIMIT 1
        ) latest_insight ON TRUE
    """


def _fetch_analysis_rows(window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            a.analysis_id,
            a.ticket_id,
            a.category,
            a.responder_type,
            a.enriched_query,
            a.risk_level,
            a.sentiment,
            a.routing_target,
            a.summary,
            a.analyzed_at,
            t.title,
            t.status,
            t.source_type,
            t.inquiry_created_at,
            u.nickname,
            latest_insight.insight_id,
            latest_insight.content_summary,
            latest_insight.insight_category,
            latest_insight.insight_sentiment,
            latest_insight.insight_risk_level,
            latest_insight.pattern_risk_level,
            latest_insight.insight_created_at
        FROM ticket_analysis a
        JOIN qa_ticket t ON t.ticket_id = a.ticket_id
        LEFT JOIN community_users u ON u.user_id = t.user_id
        {_latest_insight_join_sql()}
        WHERE a.analyzed_at >= %s
          AND a.analyzed_at < %s
        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    """
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_all(cur, sql, (window_start, window_end))


# ──────────────────────────────────────────────────────────────────────────────
# 페이로드 빌드 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_text(value: object, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _distribution(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(_normalize_text(row.get(key)) for row in rows)
    return [{"label": label, "value": counts[label]} for label in sorted(counts, key=lambda item: (-counts[item], item))]


def _format_change(current: int | float, previous: int | float) -> str:
    if previous == 0:
        if current == 0:
            return "0"
        return f"+{current}"
    return f"{((current - previous) / previous * 100):+.1f}%"


def _pick_review_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    flagged = [
        row for row in rows
        if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"}
        or _normalize_text(row.get("routing_target")).lower() in {"urgent_alert", "human_review"}
        or _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
        or not _normalize_text(row.get("summary"), fallback="").strip()
    ]
    return flagged[:limit] if flagged else rows[:limit]


def _build_analysis_rows_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "analysis_id": row.get("analysis_id"),
            "ticket_id": row.get("ticket_id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "source_type": row.get("source_type"),
            "category": row.get("category"),
            "responder_type": row.get("responder_type"),
            "enriched_query": row.get("enriched_query"),
            "risk_level": row.get("risk_level"),
            "sentiment": row.get("sentiment"),
            "routing_target": row.get("routing_target"),
            "summary": row.get("summary"),
            "analyzed_at": row.get("analyzed_at").isoformat() if row.get("analyzed_at") else None,
        }
        for row in rows
    ]


def _build_report_payload(
    *,
    window: dict[str, Any],
    previous_window: dict[str, Any],
    current_metrics: dict[str, Any],
    previous_metrics: dict[str, Any],
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    requests: dict[str, Any],
    alerts: dict[str, Any],
    ai_interp: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    total_current = len(current_rows)
    total_previous = len(previous_rows)
    distinct_ticket_ids = len({row.get("ticket_id") for row in current_rows if row.get("ticket_id") is not None})

    high_risk_count = sum(1 for row in current_rows if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    urgent_count = sum(1 for row in current_rows if _normalize_text(row.get("routing_target")).lower() == "urgent_alert")
    human_review_count = sum(1 for row in current_rows if _normalize_text(row.get("routing_target")).lower() == "human_review")
    negative_sentiment_count = sum(
        1 for row in current_rows if _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
    )
    blank_query_count = sum(1 for row in current_rows if not _normalize_text(row.get("enriched_query"), fallback="").strip())
    blank_summary_count = sum(1 for row in current_rows if not _normalize_text(row.get("summary"), fallback="").strip())
    insight_high_count = sum(
        1 for row in current_rows
        if _normalize_text(row.get("insight_risk_level")).lower() in {"high", "critical"}
        or _normalize_text(row.get("pattern_risk_level")).lower() in {"high", "critical"}
    )
    avg_analysis_age_minutes = safe_average(
        [
            (generated_at - row["analyzed_at"]).total_seconds() / 60.0
            for row in current_rows
            if row.get("analyzed_at") is not None
        ]
    )

    summary_section = {
        "analysis_count": total_current,
        "distinct_ticket_count": distinct_ticket_ids,
        "repeat_analysis_count": total_current - distinct_ticket_ids,
        "high_risk_count": high_risk_count,
        "negative_sentiment_count": negative_sentiment_count,
        "human_review_count": human_review_count,
        "urgent_alert_count": urgent_count,
        "blank_query_count": blank_query_count,
        "blank_summary_count": blank_summary_count,
        "analysis_freshness_hours": None if avg_analysis_age_minutes is None else avg_analysis_age_minutes / 60.0,
        "high_risk_rate": rate(high_risk_count, total_current),
        "negative_sentiment_rate": rate(negative_sentiment_count, total_current),
        "human_review_rate": rate(human_review_count, total_current),
        "urgent_alert_rate": rate(urgent_count, total_current),
        "blank_query_rate": rate(blank_query_count, total_current),
        "blank_summary_rate": rate(blank_summary_count, total_current),
        "insight_high_rate": rate(insight_high_count, total_current),
        # 7개 핵심 KPI (weekly_metrics에서 직접 집계한 값)
        "response_rate": current_metrics.get("response_rate", 0.0),
        "analysis_coverage_rate": current_metrics.get("analysis_coverage_rate", 0.0),
        "draft_coverage_rate": current_metrics.get("draft_coverage_rate", 0.0),
        "draft_ticket_rate": current_metrics.get("draft_ticket_rate", 0.0),
        "final_response_ticket_rate": current_metrics.get("final_response_ticket_rate", 0.0),
        "draft_count": current_metrics.get("draft_count", 0),
        "safety_check_count": current_metrics.get("safety_check_count", 0),
        "ticket_counts": {
            "total": current_metrics.get("total_tickets", 0),
        },
    }

    prev_high_risk = sum(1 for row in previous_rows if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    prev_negative = sum(1 for row in previous_rows if _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"})
    prev_human_review = sum(1 for row in previous_rows if _normalize_text(row.get("routing_target")).lower() == "human_review")

    comparisons = {
        "analysis_count": {
            "current": total_current,
            "previous": total_previous,
            "change": total_current - total_previous,
            "change_rate": _format_change(total_current, total_previous),
        },
        "high_risk_count": {
            "current": high_risk_count,
            "previous": prev_high_risk,
            "change_rate": _format_change(high_risk_count, prev_high_risk),
        },
        "negative_sentiment_count": {
            "current": negative_sentiment_count,
            "previous": prev_negative,
            "change_rate": _format_change(negative_sentiment_count, prev_negative),
        },
        "human_review_count": {
            "current": human_review_count,
            "previous": prev_human_review,
            "change_rate": _format_change(human_review_count, prev_human_review),
        },
    }

    review_rows = _pick_review_rows(current_rows, limit=12)
    row_interpretations = generate_review_row_interpretations(review_rows)
    interp_by_key = {
        (item.get("analysis_id"), item.get("ticket_id")): item.get("interpretation")
        for item in row_interpretations
    }
    review_rows = [
        {
            **row,
            "ai_row_interpretation": interp_by_key.get((row.get("analysis_id"), row.get("ticket_id")), ""),
        }
        for row in review_rows
    ]

    window_payload = {
        "days": int(window["days"]),
        "window_start": window["window_start"].isoformat(),
        "window_end": window["window_end"].isoformat(),
    }
    prev_window_payload = {
        "days": int(previous_window["days"]),
        "window_start": previous_window["window_start"].isoformat(),
        "window_end": previous_window["window_end"].isoformat(),
    }

    report = {
        "title": f"운영 주간 보고서 - {window['window_end'].date().isoformat()}",
        "generated_at": generated_at.isoformat(),
        "window": window_payload,
        "previous_window": prev_window_payload,
        "summary": summary_section,
        "comparisons": comparisons,
        "category_distribution": _distribution(current_rows, "category"),
        "responder_distribution": _distribution(current_rows, "responder_type"),
        "risk_distribution": _distribution(current_rows, "risk_level"),
        "sentiment_distribution": _distribution(current_rows, "sentiment"),
        "routing_distribution": _distribution(current_rows, "routing_target"),
        "analysis_rows": _build_analysis_rows_payload(current_rows),
        "review_rows": review_rows,
        "top_requests": requests,
        "spike_alerts": alerts,
        "ai_interpretation": ai_interp,
        "narrative_insights": ai_interp.get("bullets", []),
        "column_insights": [
            {
                "column": "AI 종합 해석",
                "metric": ai_interp.get("headline", ""),
                "insight": ai_interp.get("summary", ""),
                "severity": "info",
            },
            *[
                {
                    "column": "바로 볼 내용",
                    "metric": f"항목 {i}",
                    "insight": item,
                    "severity": "info",
                }
                for i, item in enumerate(ai_interp.get("bullets", []), start=1)
            ],
        ],
        "report_sections": [
            {"kind": "heading", "text": ai_interp.get("headline", "AI 종합 해석")},
            {"kind": "body", "text": ai_interp.get("summary", "")},
            *[{"kind": "bullet", "text": item} for item in ai_interp.get("bullets", [])],
            {"kind": "heading", "text": "우선 확인 문의"},
            *[
                {
                    "kind": "table_row",
                    "text": (
                        f"#{row['ticket_id']} | {row['category']} | {row['risk_level']} | "
                        f"{row['routing_target']} | {shorten(str(row.get('ai_row_interpretation') or ''), width=80, placeholder='...')}"
                    ),
                }
                for row in review_rows
            ],
        ],
    }
    return report


# ──────────────────────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────────────────────

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

    window = date_range.get_window(days, now=generated_at)
    previous_window = date_range.get_previous_window(window)

    current_metrics = weekly_metrics.fetch(window)
    previous_metrics = weekly_metrics.fetch(previous_window)

    current_rows = _fetch_analysis_rows(window["window_start"], window["window_end"])
    previous_rows = _fetch_analysis_rows(previous_window["window_start"], previous_window["window_end"])

    requests = top_requests.fetch(window)
    alerts = spike_alerts.detect(window)
    ai_interp = ai_summary.generate(current_metrics, requests, alerts)

    report = _build_report_payload(
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
        pdf_bytes = pdf_module.render_report_pdf(report)

    slack_result: dict[str, Any] | None = None
    if send_to_slack:
        if not slack_channel:
            raise ValueError("send_to_slack=True 이면 slack_channel 이 필요합니다")
        filename = f"weekly_report_{days}d_{generated_at.date().isoformat()}.pdf"
        slack_result = slack_module.send_weekly_report_pdf(
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
