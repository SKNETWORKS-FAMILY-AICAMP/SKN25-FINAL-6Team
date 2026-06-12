"""주간 보고서 전체 페이로드 조립."""

from __future__ import annotations

from datetime import datetime
from textwrap import shorten
from typing import Any

from ai.row_interpret import generate_review_row_interpretations
from build.distributions import normalize_text, distribution, format_change
from build.review_rows import pick_review_rows, build_analysis_rows_payload
from utils.stats import rate, safe_average


def build_report_payload(
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

    high_risk_count = sum(1 for row in current_rows if normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    urgent_count = sum(1 for row in current_rows if normalize_text(row.get("routing_target")).lower() == "urgent_alert")
    human_review_count = sum(1 for row in current_rows if normalize_text(row.get("routing_target")).lower() == "human_review")
    negative_sentiment_count = sum(
        1 for row in current_rows if normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
    )
    blank_query_count = sum(1 for row in current_rows if not normalize_text(row.get("enriched_query"), fallback="").strip())
    blank_summary_count = sum(1 for row in current_rows if not normalize_text(row.get("summary"), fallback="").strip())
    insight_high_count = sum(
        1 for row in current_rows
        if normalize_text(row.get("insight_risk_level")).lower() in {"high", "critical"}
        or normalize_text(row.get("pattern_risk_level")).lower() in {"high", "critical"}
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

    prev_high_risk = sum(1 for row in previous_rows if normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    prev_negative = sum(1 for row in previous_rows if normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"})
    prev_human_review = sum(1 for row in previous_rows if normalize_text(row.get("routing_target")).lower() == "human_review")

    comparisons = {
        "analysis_count": {
            "current": total_current,
            "previous": total_previous,
            "change": total_current - total_previous,
            "change_rate": format_change(total_current, total_previous),
        },
        "high_risk_count": {
            "current": high_risk_count,
            "previous": prev_high_risk,
            "change_rate": format_change(high_risk_count, prev_high_risk),
        },
        "negative_sentiment_count": {
            "current": negative_sentiment_count,
            "previous": prev_negative,
            "change_rate": format_change(negative_sentiment_count, prev_negative),
        },
        "human_review_count": {
            "current": human_review_count,
            "previous": prev_human_review,
            "change_rate": format_change(human_review_count, prev_human_review),
        },
    }

    review_rows = pick_review_rows(current_rows, limit=12)
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

    return {
        "title": f"운영 주간 보고서 - {window['window_end'].date().isoformat()}",
        "generated_at": generated_at.isoformat(),
        "window": window_payload,
        "previous_window": prev_window_payload,
        "summary": summary_section,
        "comparisons": comparisons,
        "category_distribution": distribution(current_rows, "category"),
        "responder_distribution": distribution(current_rows, "responder_type"),
        "risk_distribution": distribution(current_rows, "risk_level"),
        "sentiment_distribution": distribution(current_rows, "sentiment"),
        "routing_distribution": distribution(current_rows, "routing_target"),
        "analysis_rows": build_analysis_rows_payload(current_rows),
        "review_rows": review_rows,
        "top_requests": requests,
        "spike_alerts": alerts,
        "ai_interpretation": ai_interp,
        "narrative_insights": [
            f"[{a.get('category', '')}] {a.get('action', '')}"
            for a in ai_interp.get("actions", [])
        ],
        "column_insights": [
            {
                "column": "AI 종합 해석",
                "metric": ai_interp.get("headline", ""),
                "insight": ai_interp.get("headline", ""),
                "severity": "info",
            },
            *[
                {
                    "column": "기획팀 권장 액션",
                    "metric": f"#{a.get('rank', i + 1)} {a.get('category', '')}",
                    "insight": f"{a.get('action', '')} — {a.get('reason', '')}",
                    "severity": "info",
                }
                for i, a in enumerate(ai_interp.get("actions", []))
            ],
        ],
        "report_sections": [
            {"kind": "heading", "text": ai_interp.get("headline", "AI 권장 액션")},
            *[
                {
                    "kind": "bullet",
                    "text": (
                        f"#{a.get('rank', i + 1)} [{a.get('category', '')}] "
                        f"{a.get('action', '')} — {a.get('reason', '')}"
                    ),
                }
                for i, a in enumerate(ai_interp.get("actions", []))
            ],
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
