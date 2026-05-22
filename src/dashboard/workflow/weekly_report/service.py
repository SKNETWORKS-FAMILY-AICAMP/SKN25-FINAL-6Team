"""Data loading and report composition helpers for the weekly dashboard report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from textwrap import shorten
from typing import Any

from psycopg.rows import dict_row

from src.common.db.connection import db_connection
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
    insight_risk_counts = _counts(current_rows, "insight_risk_level")
    pattern_risk_counts = _counts(current_rows, "pattern_risk_level")

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

    previous_category_counts = _counts(previous_rows, "category")
    previous_risk_counts = _counts(previous_rows, "risk_level")
    previous_sentiment_counts = _counts(previous_rows, "sentiment")
    previous_routing_counts = _counts(previous_rows, "routing_target")
    previous_responder_counts = _counts(previous_rows, "responder_type")

    total_previous = total_previous or 0
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

    narrative_insights: list[str] = []
    if current_total == 0:
        narrative_insights.append("이번 기간 ticket_analysis 데이터가 없습니다.")
    else:
        if high_risk_rate >= 0.2 or insight_high_rate >= 0.2:
            narrative_insights.append(
                f"고위험 분석 비중이 {high_risk_rate:.1%}이며, 인사이트 위험도까지 포함하면 {insight_high_rate:.1%}로 운영자 검토가 필요합니다."
            )
        if negative_sentiment_rate >= 0.25:
            narrative_insights.append(
                f"부정 감성 비중이 {negative_sentiment_rate:.1%}로 높아 게임 체감 이슈 또는 정책 불만을 우선 점검해야 합니다."
            )
        if human_review_rate >= 0.15 or current_final_response_rate < current_draft_ticket_rate:
            narrative_insights.append(
                f"human_review 비중이 {human_review_rate:.1%}이며 최종 응답 전환율이 초안 커버리지 대비 낮아 수동 검수 병목을 확인해야 합니다."
            )
        if blank_query_rate >= 0.05 or blank_summary_rate >= 0.05:
            narrative_insights.append(
                f"enriched_query 누락률 {blank_query_rate:.1%}, summary 누락률 {blank_summary_rate:.1%}로 분석 입력 품질 보완이 필요합니다."
            )
        if avg_analysis_age_minutes is not None and avg_analysis_age_minutes >= 24 * 60:
            narrative_insights.append(
                f"분석 신선도가 평균 {format_minutes(avg_analysis_age_minutes)} 수준으로 지연되어 재분석 배치나 라우팅 기준 점검이 필요합니다."
            )
        if current_category_top and current_category_top[0]["value"] / current_total >= 0.4:
            narrative_insights.append(
                f"{current_category_top[0]['label']} 카테고리가 전체의 {current_category_top[0]['value'] / current_total:.1%}를 차지해 특정 이슈에 쏠림이 있습니다."
            )

    column_insights = [
        {
            "column": "analysis_id",
            "metric": f"{min(row['analysis_id'] for row in current_rows) if current_rows else '-'} ~ {max(row['analysis_id'] for row in current_rows) if current_rows else '-'}",
            "insight": f"이번 기간 {current_total}건의 분석이 생성되었고, 분석 ID는 증가 순으로 정상 누적되었습니다.",
            "severity": "info",
        },
        {
            "column": "ticket_id",
            "metric": f"{distinct_ticket_ids_current} tickets / {repeat_analysis_count} repeated analyses",
            "insight": "동일 티켓의 재분석 비중이 높으면 검수 루프 또는 재판단 이슈가 반복된다는 뜻입니다.",
            "severity": "warning" if repeat_analysis_count > distinct_ticket_ids_current * 0.2 else "info",
        },
        {
            "column": "category",
            "metric": ", ".join(f"{item['label']} {item['value']}" for item in current_category_top) or "-",
            "insight": "상위 카테고리를 중심으로 FAQ 보강, 게임기획 조정, 정책 수정 후보를 확인합니다.",
            "severity": "info",
        },
        {
            "column": "responder_type",
            "metric": ", ".join(f"{item['label']} {item['value']}" for item in current_responder_top) or "-",
            "insight": "자동/수동 응답의 비중을 통해 운영 인력과 자동화 경로의 균형을 점검합니다.",
            "severity": "info",
        },
        {
            "column": "enriched_query",
            "metric": f"avg {avg_query_length:.1f} chars / blank {blank_query_rate:.1%}" if avg_query_length is not None else f"blank {blank_query_rate:.1%}",
            "insight": "보강 질의가 충분히 길고 명확한지 확인하면 분석 모델이 올바른 문맥을 받는지 판단할 수 있습니다.",
            "severity": _severity_for_rate(blank_query_rate, high=0.1, warning=0.05),
        },
        {
            "column": "risk_level",
            "metric": ", ".join(f"{item['label']} {item['value']}" for item in current_risk_top) or "-",
            "insight": f"HIGH/critical 비율은 {high_risk_rate:.1%}이며, 위험도 급증 시 운영자 우선 검토로 연결해야 합니다.",
            "severity": _severity_for_rate(high_risk_rate, high=0.2, warning=0.1),
        },
        {
            "column": "sentiment",
            "metric": ", ".join(f"{item['label']} {item['value']}" for item in current_sentiment_top) or "-",
            "insight": f"negative 감성 비중은 {negative_sentiment_rate:.1%}로, 커뮤니티 체감 악화 여부를 빨리 확인해야 합니다.",
            "severity": _severity_for_rate(negative_sentiment_rate, high=0.25, warning=0.15),
        },
        {
            "column": "routing_target",
            "metric": ", ".join(f"{item['label']} {item['value']}" for item in current_routing_top) or "-",
            "insight": f"human_review {human_review_rate:.1%}, urgent_alert {urgent_rate:.1%}는 운영 인력 부담과 긴급성의 직접 신호입니다.",
            "severity": "critical" if urgent_rate >= 0.05 else "warning" if human_review_rate >= 0.15 else "info",
        },
        {
            "column": "summary",
            "metric": f"avg {avg_summary_length:.1f} chars / blank {blank_summary_rate:.1%}" if avg_summary_length is not None else f"blank {blank_summary_rate:.1%}",
            "insight": "summary가 짧거나 누락되면 티켓의 핵심 원인을 빠르게 읽기 어렵습니다.",
            "severity": _severity_for_rate(blank_summary_rate, high=0.1, warning=0.05),
        },
        {
            "column": "analyzed_at",
            "metric": "avg " + format_minutes(avg_analysis_age_minutes) if avg_analysis_age_minutes is not None else "-",
            "insight": "분석 신선도는 운영 대응 속도와 직결되므로 평균 지연이 길어지면 배치 주기를 조정해야 합니다.",
            "severity": "warning" if avg_analysis_age_minutes is not None and avg_analysis_age_minutes >= 12 * 60 else "info",
        },
    ]

    review_rows = _pick_rows(current_rows, limit=12)

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

    report_title = f"Dashboard Weekly Report - {window['window_end'].date().isoformat()}"

    return {
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
        "narrative_insights": narrative_insights,
        "column_insights": column_insights,
        "category_distribution": _distribution(current_rows, "category"),
        "responder_distribution": _distribution(current_rows, "responder_type"),
        "risk_distribution": _distribution(current_rows, "risk_level"),
        "sentiment_distribution": _distribution(current_rows, "sentiment"),
        "routing_distribution": _distribution(current_rows, "routing_target"),
        "analysis_rows": analysis_table_rows,
        "review_rows": review_rows,
        "dashboard_summary": dashboard_summary,
        "report_sections": [
            {
                "kind": "heading",
                "text": "Executive summary",
            },
            *[{"kind": "bullet", "text": item} for item in narrative_insights],
            {
                "kind": "heading",
                "text": "Column insights",
            },
            *[
                {
                    "kind": "bullet",
                    "text": f"{item['column']}: {item['metric']} | {item['insight']}",
                }
                for item in column_insights
            ],
            {
                "kind": "heading",
                "text": "Priority review tickets",
            },
            *[
                {
                    "kind": "table_row",
                    "text": (
                        f"#{row['ticket_id']} | {row['category']} | {row['risk_level']} | "
                        f"{row['routing_target']} | {shorten(str(row['summary'] or ''), width=80, placeholder='...')}"
                    ),
                }
                for row in review_rows
            ],
        ],
    }

