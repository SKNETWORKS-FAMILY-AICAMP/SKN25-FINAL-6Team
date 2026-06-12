"""카테고리별 주간 지표 + 7개 핵심값 직접 쿼리.

SQL 출처: (삭제 전) workflow/service.py
  - response_rate 등: _overview_summary() response_metrics 쿼리 (L141-183)
  - draft_count, draft_ticket_rate: _quality_summary() draft_summary 쿼리 (L493-513)
  - final_response_ticket_rate: final_response_summary 쿼리 (L544-560)
  - safety_check_count: _risk_summary() safety_score_summary 쿼리 (L347-362)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from db.connection import _fetch_one, _fetch_all, db_connection, dict_row
from utils.stats import rate


def fetch(window: dict[str, Any]) -> dict[str, Any]:
    """window 기간의 7개 핵심 KPI + 카테고리별 집계를 반환한다."""
    start: datetime = window["window_start"]
    end: datetime = window["window_end"]

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            coverage = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT t.ticket_id) AS total_tickets,
                    COUNT(DISTINCT t.ticket_id)
                        FILTER (WHERE latest_response.response_id IS NOT NULL)
                        AS responded_tickets,
                    COUNT(DISTINCT d_any.ticket_id) AS draft_tickets,
                    COUNT(DISTINCT a_any.ticket_id) AS analyzed_tickets
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT response_id
                    FROM final_response fr
                    WHERE fr.ticket_id = t.ticket_id
                    ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
                    LIMIT 1
                ) latest_response ON TRUE
                LEFT JOIN LATERAL (
                    SELECT ticket_id
                    FROM answer_draft d
                    WHERE d.ticket_id = t.ticket_id
                    LIMIT 1
                ) d_any ON TRUE
                LEFT JOIN LATERAL (
                    SELECT ticket_id
                    FROM ticket_analysis a
                    WHERE a.ticket_id = t.ticket_id
                    LIMIT 1
                ) a_any ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                """,
                (start, end),
            ) or {}

            draft = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT d.draft_id) AS draft_count,
                    COUNT(DISTINCT d.ticket_id) AS draft_ticket_count
                FROM qa_ticket t
                LEFT JOIN answer_draft d ON d.ticket_id = t.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                """,
                (start, end),
            ) or {}

            final_resp = _fetch_one(
                cur,
                """
                SELECT COUNT(DISTINCT fr.ticket_id) AS final_response_ticket_count
                FROM qa_ticket t
                LEFT JOIN final_response fr ON fr.ticket_id = t.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                """,
                (start, end),
            ) or {}

            safety = _fetch_one(
                cur,
                """
                SELECT COUNT(*) AS safety_check_count
                FROM safety_results s
                JOIN answer_draft d ON d.draft_id = s.draft_id
                JOIN qa_ticket t ON t.ticket_id = d.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                """,
                (start, end),
            ) or {}

            category_rows = _fetch_all(
                cur,
                """
                SELECT
                    COALESCE(latest_a.category, 'unknown') AS category,
                    COUNT(DISTINCT t.ticket_id) AS count
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT category
                    FROM ticket_analysis a
                    WHERE a.ticket_id = t.ticket_id
                    ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                    LIMIT 1
                ) latest_a ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1
                ORDER BY count DESC, category ASC
                """,
                (start, end),
            )

    total = int(coverage.get("total_tickets") or 0)
    responded = int(coverage.get("responded_tickets") or 0)
    draft_tickets = int(coverage.get("draft_tickets") or 0)
    analyzed = int(coverage.get("analyzed_tickets") or 0)
    draft_ticket_count = int(draft.get("draft_ticket_count") or 0)
    final_ticket_count = int(final_resp.get("final_response_ticket_count") or 0)

    return {
        "response_rate": rate(responded, total),
        "analysis_coverage_rate": rate(analyzed, total),
        "draft_coverage_rate": rate(draft_tickets, total),
        "draft_ticket_rate": rate(draft_ticket_count, total),
        "final_response_ticket_rate": rate(final_ticket_count, total),
        "draft_count": int(draft.get("draft_count") or 0),
        "safety_check_count": int(safety.get("safety_check_count") or 0),
        "total_tickets": total,
        "category_counts": [
            {"category": row["category"], "count": int(row["count"])}
            for row in category_rows
        ],
    }
