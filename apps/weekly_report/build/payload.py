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
    """모든 데이터 소스를 받아 PDF·Slack 렌더러가 소비할 단일 페이로드 dict를 조립한다.

    반환값의 구조는 output/pdf.py와 output/slack.py가 키 이름을 직접 참조하므로
    키를 변경하면 렌더러도 함께 수정해야 한다.
    """
    # ── 기본 집계 ─────────────────────────────────────────────────────────────
    total_current = len(current_rows)
    total_previous = len(previous_rows)
    # ticket_id 기준 중복 제거 — 한 티켓이 여러 번 분석된 경우(재분석)를 구분한다.
    distinct_ticket_ids = len({row.get("ticket_id") for row in current_rows if row.get("ticket_id") is not None})

    # normalize_text를 통해 None/빈 값을 "unknown"으로 치환한 뒤 비교한다.
    high_risk_count = sum(1 for row in current_rows if normalize_text(row.get("risk_level")).lower() in {"high", "critical"})
    urgent_count = sum(1 for row in current_rows if normalize_text(row.get("routing_target")).lower() == "urgent_alert")
    human_review_count = sum(1 for row in current_rows if normalize_text(row.get("routing_target")).lower() == "human_review")
    negative_sentiment_count = sum(
        1 for row in current_rows if normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
    )
    # enriched_query나 summary가 비어 있는 행은 분석 파이프라인 문제를 나타낸다.
    blank_query_count = sum(1 for row in current_rows if not normalize_text(row.get("enriched_query"), fallback="").strip())
    blank_summary_count = sum(1 for row in current_rows if not normalize_text(row.get("summary"), fallback="").strip())
    # insight_risk_level 또는 pattern_risk_level 중 하나라도 high/critical이면 집계에 포함한다.
    insight_high_count = sum(
        1 for row in current_rows
        if normalize_text(row.get("insight_risk_level")).lower() in {"high", "critical"}
        or normalize_text(row.get("pattern_risk_level")).lower() in {"high", "critical"}
    )
    # 분석 신선도: analyzed_at ~ generated_at 차이의 평균 (분 단위).
    avg_analysis_age_minutes = safe_average(
        [
            (generated_at - row["analyzed_at"]).total_seconds() / 60.0
            for row in current_rows
            if row.get("analyzed_at") is not None
        ]
    )

    # ── 요약 섹션 ─────────────────────────────────────────────────────────────
    # analysis_rows 기반 집계와 db.metrics 기반 KPI를 하나의 dict에 합친다.
    summary_section = {
        "analysis_count": total_current,
        "distinct_ticket_count": distinct_ticket_ids,
        # 재분석 횟수 = 전체 분석 건수 - 고유 티켓 수
        "repeat_analysis_count": total_current - distinct_ticket_ids,
        "high_risk_count": high_risk_count,
        "negative_sentiment_count": negative_sentiment_count,
        "human_review_count": human_review_count,
        "urgent_alert_count": urgent_count,
        "blank_query_count": blank_query_count,
        "blank_summary_count": blank_summary_count,
        # 시간 단위로 변환해 "N시간 전 분석" 표현에 바로 사용할 수 있게 한다.
        "analysis_freshness_hours": None if avg_analysis_age_minutes is None else avg_analysis_age_minutes / 60.0,
        "high_risk_rate": rate(high_risk_count, total_current),
        "negative_sentiment_rate": rate(negative_sentiment_count, total_current),
        "human_review_rate": rate(human_review_count, total_current),
        "urgent_alert_rate": rate(urgent_count, total_current),
        "blank_query_rate": rate(blank_query_count, total_current),
        "blank_summary_rate": rate(blank_summary_count, total_current),
        "insight_high_rate": rate(insight_high_count, total_current),
        # db.metrics에서 집계한 KPI (티켓 기준 비율)
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

    # ── 전주 비교 섹션 ────────────────────────────────────────────────────────
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

    # ── 우선 확인 행 + AI 해석 ────────────────────────────────────────────────
    # 최대 12개 행을 선별한 뒤 LLM으로 각 행의 한 줄 해석을 생성한다.
    review_rows = pick_review_rows(current_rows, limit=12)
    row_interpretations = generate_review_row_interpretations(review_rows)
    # (analysis_id, ticket_id) 복합 키로 LLM 해석을 원본 행에 매핑한다.
    interp_by_key = {
        (item.get("analysis_id"), item.get("ticket_id")): item.get("interpretation")
        for item in row_interpretations
    }
    review_rows = [
        {
            **row,
            # 해석이 없으면 빈 문자열로 채워 렌더러가 None을 처리하지 않아도 된다.
            "ai_row_interpretation": interp_by_key.get((row.get("analysis_id"), row.get("ticket_id")), ""),
        }
        for row in review_rows
    ]

    # ── window를 JSON 직렬화 가능한 형태로 변환 ───────────────────────────────
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
        # 5가지 분포 — PDF 차트 섹션에서 각각 파이 차트로 렌더링된다.
        "category_distribution": distribution(current_rows, "category"),
        "responder_distribution": distribution(current_rows, "responder_type"),
        "risk_distribution": distribution(current_rows, "risk_level"),
        "sentiment_distribution": distribution(current_rows, "sentiment"),
        "routing_distribution": distribution(current_rows, "routing_target"),
        # 전체 분석 행 (PDF 원본 미리보기 테이블용)
        "analysis_rows": build_analysis_rows_payload(current_rows),
        # 우선 확인 행 (AI 해석 포함)
        "review_rows": review_rows,
        "top_requests": requests,
        "spike_alerts": alerts,
        "ai_interpretation": ai_interp,
        # narrative_insights: Slack 단순 텍스트 블록용 요약 리스트
        "narrative_insights": [
            f"[{a.get('category', '')}] {a.get('action', '')}"
            for a in ai_interp.get("actions", [])
        ],
        # column_insights: 대시보드 테이블 형식으로 AI 해석을 표시할 때 사용
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
        # report_sections: heading/bullet/table_row 형식의 구조화된 본문 (텍스트 렌더링용)
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
                    # shorten으로 ai_row_interpretation을 80자로 잘라 단일 행 길이를 제한한다.
                    "text": (
                        f"#{row['ticket_id']} | {row['category']} | {row['risk_level']} | "
                        f"{row['routing_target']} | {shorten(str(row.get('ai_row_interpretation') or ''), width=80, placeholder='...')}"
                    ),
                }
                for row in review_rows
            ],
        ],
    }
