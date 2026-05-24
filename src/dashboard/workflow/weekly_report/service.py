"""Data loading and report composition helpers for the weekly dashboard report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from textwrap import shorten
from typing import Any

from psycopg.rows import dict_row

from src.common.db.connection import db_connection
from src.dashboard.ai import generate_dashboard_interpretation, generate_review_row_interpretations
from src.dashboard.util import build_window, clamp_days, format_minutes, rate, safe_average
from src.dashboard.workflow.graph import run_dashboard_workflow


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _normalize_text(value: object, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _latest_analysis_join_sql() -> str:
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


def _analysis_rows_sql() -> str:
    return f"""
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
        {_latest_analysis_join_sql()}
        WHERE a.analyzed_at >= %s
          AND a.analyzed_at < %s
        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    """


def _fetch_analysis_rows(window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_all(cur, _analysis_rows_sql(), (window_start, window_end))


def fetch_weekly_report_data(days: int, *, now: datetime | None = None) -> dict[str, Any]:
    """Read the dashboard summary and ticket analysis rows for the weekly report."""

    current_now = now or datetime.now()
    days = clamp_days(days)
    window = build_window(days, now=current_now)
    previous_window = {
        "days": days,
        "window_start": window["window_start"] - timedelta(days=days),
        "window_end": window["window_start"],
    }

    dashboard_summary = run_dashboard_workflow("all", days)
    current_rows = _fetch_analysis_rows(window["window_start"], window["window_end"])
    previous_rows = _fetch_analysis_rows(previous_window["window_start"], previous_window["window_end"])

    return {
        "window": window,
        "previous_window": previous_window,
        "dashboard_summary": dashboard_summary,
        "current_rows": current_rows,
        "previous_rows": previous_rows,
        "generated_at": current_now,
    }


def _distribution(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(_normalize_text(row.get(key)) for row in rows)
    return [{"label": label, "value": counts[label]} for label in sorted(counts, key=lambda item: (-counts[item], item))]


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(_normalize_text(row.get(key)) for row in rows)
    return dict(counts)


def _format_change(current: int | float, previous: int | float) -> str:
    if previous == 0:
        if current == 0:
            return "0"
        return f"+{current}"
    change = (current - previous) / previous * 100
    return f"{change:+.1f}%"


def _severity_for_rate(rate_value: float, *, high: float, warning: float) -> str:
    if rate_value >= high:
        return "critical"
    if rate_value >= warning:
        return "warning"
    return "info"


def _top_items(counts: dict[str, int], *, limit: int = 3) -> list[dict[str, Any]]:
    return [
        {"label": label, "value": value}
        for label, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _pick_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    flagged = [
        row
        for row in rows
        if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"}
        or _normalize_text(row.get("routing_target")).lower() in {"urgent_alert", "human_review"}
        or _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
        or not _normalize_text(row.get("summary"), fallback="").strip()
    ]
    if flagged:
        return flagged[:limit]
    return rows[:limit]


def build_weekly_report_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Turn raw DB rows and dashboard summary data into a weekly report payload."""

    dashboard_summary = data["dashboard_summary"]
    current_rows = data["current_rows"]
    previous_rows = data["previous_rows"]
    window = data["window"]
    previous_window = data["previous_window"]
    generated_at = data["generated_at"]

    total_current = len(current_rows)
    total_previous = len(previous_rows)
    ticket_ids_current = [row.get("ticket_id") for row in current_rows if row.get("ticket_id") is not None]
    distinct_ticket_ids_current = len(set(ticket_ids_current))
    repeat_analysis_count = total_current - distinct_ticket_ids_current

    category_counts = _counts(current_rows, "category")
    responder_counts = _counts(current_rows, "responder_type")
    risk_counts = _counts(current_rows, "risk_level")
    sentiment_counts = _counts(current_rows, "sentiment")
    routing_counts = _counts(current_rows, "routing_target")
    summary_section = dashboard_summary["overview"]
    risk_section = dashboard_summary["risk"]
    quality_section = dashboard_summary["quality"]

    response_metrics = summary_section.get("response_metrics", {})
    coverage_metrics = quality_section.get("coverage_metrics", {})
    draft_summary = quality_section.get("draft_summary", {})
    safety_summary = risk_section.get("safety_score_summary", {})

    avg_query_length = safe_average([len(str(row.get("enriched_query") or "")) for row in current_rows])
    avg_summary_length = safe_average([len(str(row.get("summary") or "")) for row in current_rows])
    avg_analysis_age_minutes = safe_average(
        [
            (generated_at - row["analyzed_at"]).total_seconds() / 60.0
            for row in current_rows
            if row.get("analyzed_at") is not None
        ]
    )

    blank_query_count = sum(1 for row in current_rows if not _normalize_text(row.get("enriched_query"), fallback="").strip())
    blank_summary_count = sum(1 for row in current_rows if not _normalize_text(row.get("summary"), fallback="").strip())
    high_risk_count = sum(1 for row in current_rows if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    urgent_count = sum(1 for row in current_rows if _normalize_text(row.get("routing_target")).lower() == "urgent_alert")
    human_review_count = sum(1 for row in current_rows if _normalize_text(row.get("routing_target")).lower() == "human_review")
    negative_sentiment_count = sum(1 for row in current_rows if _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"})
    insight_high_count = sum(
        1
        for row in current_rows
        if _normalize_text(row.get("insight_risk_level")).lower() in {"high", "critical"}
        or _normalize_text(row.get("pattern_risk_level")).lower() in {"high", "critical"}
    )

    current_category_top = _top_items(category_counts, limit=3)
    current_risk_top = _top_items(risk_counts, limit=3)
    current_sentiment_top = _top_items(sentiment_counts, limit=3)
    current_routing_top = _top_items(routing_counts, limit=3)
    current_responder_top = _top_items(responder_counts, limit=3)

    current_total = total_current or 0

    high_risk_rate = rate(high_risk_count, current_total)
    negative_sentiment_rate = rate(negative_sentiment_count, current_total)
    human_review_rate = rate(human_review_count, current_total)
    urgent_rate = rate(urgent_count, current_total)
    blank_query_rate = rate(blank_query_count, current_total)
    blank_summary_rate = rate(blank_summary_count, current_total)
    insight_high_rate = rate(insight_high_count, current_total)

    current_dashboard_overview = summary_section.get("ticket_counts", {})
    current_response_rate = response_metrics.get("response_rate") or 0.0
    current_analysis_coverage = response_metrics.get("analysis_coverage_rate") or 0.0
    current_draft_coverage = response_metrics.get("draft_coverage_rate") or 0.0
    current_draft_ticket_rate = coverage_metrics.get("draft_ticket_rate") or 0.0
    current_final_response_rate = coverage_metrics.get("final_response_ticket_rate") or 0.0

    current_summary = {
        "analysis_count": current_total,
        "distinct_ticket_count": distinct_ticket_ids_current,
        "repeat_analysis_count": repeat_analysis_count,
        "high_risk_count": high_risk_count,
        "negative_sentiment_count": negative_sentiment_count,
        "human_review_count": human_review_count,
        "urgent_alert_count": urgent_count,
        "blank_query_count": blank_query_count,
        "blank_summary_count": blank_summary_count,
        "analysis_freshness_hours": None if avg_analysis_age_minutes is None else avg_analysis_age_minutes / 60.0,
        "avg_query_length": avg_query_length,
        "avg_summary_length": avg_summary_length,
        "high_risk_rate": high_risk_rate,
        "negative_sentiment_rate": negative_sentiment_rate,
        "human_review_rate": human_review_rate,
        "urgent_alert_rate": urgent_rate,
        "blank_query_rate": blank_query_rate,
        "blank_summary_rate": blank_summary_rate,
        "insight_high_rate": insight_high_rate,
        "response_rate": current_response_rate,
        "analysis_coverage_rate": current_analysis_coverage,
        "draft_coverage_rate": current_draft_coverage,
        "draft_ticket_rate": current_draft_ticket_rate,
        "final_response_ticket_rate": current_final_response_rate,
        "ticket_counts": current_dashboard_overview,
        "safety_check_count": safety_summary.get("safety_check_count") or 0,
        "draft_count": draft_summary.get("draft_count") or 0,
    }

    comparisons = {
        "analysis_count": {
            "current": current_total,
            "previous": total_previous,
            "change": current_total - total_previous,
            "change_rate": _format_change(current_total, total_previous),
        },
        "high_risk_count": {
            "current": high_risk_count,
            "previous": sum(1 for row in previous_rows if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"}),
            "change_rate": _format_change(
                high_risk_count,
                sum(1 for row in previous_rows if _normalize_text(row.get("risk_level")).lower() in {"high", "critical"}),
            ),
        },
        "negative_sentiment_count": {
            "current": negative_sentiment_count,
            "previous": sum(1 for row in previous_rows if _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}),
            "change_rate": _format_change(
                negative_sentiment_count,
                sum(1 for row in previous_rows if _normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}),
            ),
        },
        "human_review_count": {
            "current": human_review_count,
            "previous": sum(1 for row in previous_rows if _normalize_text(row.get("routing_target")).lower() == "human_review"),
            "change_rate": _format_change(
                human_review_count,
                sum(1 for row in previous_rows if _normalize_text(row.get("routing_target")).lower() == "human_review"),
            ),
        },
    }

    review_rows = _pick_rows(current_rows, limit=12)
    row_interpretations = generate_review_row_interpretations(review_rows)
    interpretation_by_key = {
        (item.get("analysis_id"), item.get("ticket_id")): item.get("interpretation")
        for item in row_interpretations
    }
    review_rows = [
        {
            **row,
            "ai_row_interpretation": interpretation_by_key.get((row.get("analysis_id"), row.get("ticket_id")), ""),
        }
        for row in review_rows
    ]

    analysis_table_rows = [
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
        for row in current_rows
    ]

    report_title = f"운영 주간 보고서 - {window['window_end'].date().isoformat()}"

    report_payload = {
        "title": report_title,
        "generated_at": generated_at.isoformat(),
        "window": {
            "days": window["days"],
            "window_start": window["window_start"].isoformat(),
            "window_end": window["window_end"].isoformat(),
        },
        "previous_window": {
            "days": previous_window["days"],
            "window_start": previous_window["window_start"].isoformat(),
            "window_end": previous_window["window_end"].isoformat(),
        },
        "summary": current_summary,
        "comparisons": comparisons,
        "category_distribution": _distribution(current_rows, "category"),
        "responder_distribution": _distribution(current_rows, "responder_type"),
        "risk_distribution": _distribution(current_rows, "risk_level"),
        "sentiment_distribution": _distribution(current_rows, "sentiment"),
        "routing_distribution": _distribution(current_rows, "routing_target"),
        "analysis_rows": analysis_table_rows,
        "review_rows": review_rows,
        "dashboard_summary": dashboard_summary,
    }
    ai_interpretation = generate_dashboard_interpretation("weekly_report", report_payload)
    report_payload["ai_interpretation"] = ai_interpretation
    report_payload["narrative_insights"] = ai_interpretation.get("bullets", [])
    report_payload["column_insights"] = [
        {
            "column": "AI 종합 해석",
            "metric": ai_interpretation.get("headline", ""),
            "insight": ai_interpretation.get("summary", ""),
            "severity": "info",
        },
        *[
            {
                "column": "바로 볼 내용",
                "metric": f"항목 {index}",
                "insight": item,
                "severity": "info",
            }
            for index, item in enumerate(ai_interpretation.get("bullets", []), start=1)
        ],
    ]
    report_payload["report_sections"] = [
        {
            "kind": "heading",
            "text": ai_interpretation.get("headline", "AI 종합 해석"),
        },
        {
            "kind": "body",
            "text": ai_interpretation.get("summary", ""),
        },
        *[{"kind": "bullet", "text": item} for item in ai_interpretation.get("bullets", [])],
        {
            "kind": "heading",
            "text": "우선 확인할 문의",
        },
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
    ]
    return report_payload
