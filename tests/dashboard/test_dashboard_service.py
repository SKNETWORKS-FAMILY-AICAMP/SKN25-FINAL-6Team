from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from src.common.db.connection import db_connection
from src.dashboard.workflow import run_dashboard_workflow, run_weekly_report_workflow


def _window_start(days: int = 30) -> datetime:
    return datetime.now() - timedelta(days=days)


def _skip_if_no_db_password() -> None:
    if not os.environ.get("DB_PASSWORD"):
        pytest.skip("DB_PASSWORD environment variable is required for dashboard DB smoke tests")


def _fetch_one(sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return {}
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))


def test_dashboard_workflow_reads_db_and_computes_kpis() -> None:
    _skip_if_no_db_password()

    days = 30
    window_start = _window_start(days)

    overview = run_dashboard_workflow("overview", days)
    risk = run_dashboard_workflow("risk", days)
    quality = run_dashboard_workflow("quality", days)

    overview_counts = _fetch_one(
        """
        SELECT
            COUNT(*) AS total_tickets,
            COUNT(*) FILTER (WHERE status = 'pending') AS pending_tickets,
            COUNT(*) FILTER (WHERE status = 'closed') AS closed_tickets
        FROM qa_ticket
        WHERE inquiry_created_at >= %s
        """,
        (window_start,),
    )
    response_metrics = _fetch_one(
        """
        SELECT
            COUNT(DISTINCT t.ticket_id) FILTER (WHERE fr.response_id IS NOT NULL) AS responded_tickets,
            COUNT(DISTINCT d.ticket_id) AS draft_tickets,
            COUNT(DISTINCT a.ticket_id) AS analyzed_tickets
        FROM qa_ticket t
        LEFT JOIN LATERAL (
            SELECT response_id
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) fr ON TRUE
        LEFT JOIN LATERAL (
            SELECT ticket_id
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            LIMIT 1
        ) d ON TRUE
        LEFT JOIN LATERAL (
            SELECT ticket_id
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            LIMIT 1
        ) a ON TRUE
        WHERE t.inquiry_created_at >= %s
        """,
        (window_start,),
    )
    quality_counts = _fetch_one(
        """
        SELECT
            COUNT(DISTINCT d.ticket_id) AS draft_tickets,
            COUNT(DISTINCT fr.ticket_id) AS final_response_tickets,
            COUNT(DISTINCT d.draft_id) AS draft_count
        FROM qa_ticket t
        LEFT JOIN answer_draft d ON d.ticket_id = t.ticket_id
        LEFT JOIN final_response fr ON fr.ticket_id = t.ticket_id
        WHERE t.inquiry_created_at >= %s
        """,
        (window_start,),
    )
    safety_counts = _fetch_one(
        """
        SELECT COUNT(*) AS safety_check_count
        FROM safety_results s
        JOIN answer_draft d ON d.draft_id = s.draft_id
        JOIN qa_ticket t ON t.ticket_id = d.ticket_id
        WHERE t.inquiry_created_at >= %s
        """,
        (window_start,),
    )

    total_tickets = int(overview_counts.get("total_tickets") or 0)
    pending_tickets = int(overview_counts.get("pending_tickets") or 0)
    closed_tickets = int(overview_counts.get("closed_tickets") or 0)
    responded_tickets = int(response_metrics.get("responded_tickets") or 0)
    draft_tickets = int(response_metrics.get("draft_tickets") or 0)
    analyzed_tickets = int(response_metrics.get("analyzed_tickets") or 0)
    draft_count = int(quality_counts.get("draft_count") or 0)
    quality_draft_tickets = int(quality_counts.get("draft_tickets") or 0)
    final_response_tickets = int(quality_counts.get("final_response_tickets") or 0)
    safety_check_count = int(safety_counts.get("safety_check_count") or 0)

    assert overview["ticket_counts"]["total"] == total_tickets
    assert overview["ticket_counts"]["pending"] == pending_tickets
    assert overview["ticket_counts"]["closed"] == closed_tickets
    assert overview["response_metrics"]["response_rate"] == pytest.approx(
        responded_tickets / total_tickets if total_tickets else 0.0
    )
    assert overview["coverage_metrics"]["draft_coverage_rate"] == pytest.approx(
        draft_tickets / total_tickets if total_tickets else 0.0
    )
    assert overview["coverage_metrics"]["analysis_coverage_rate"] == pytest.approx(
        analyzed_tickets / total_tickets if total_tickets else 0.0
    )

    assert "safety_score_summary" in risk
    assert "high_risk_tickets" in risk
    assert "safety_breach_candidates" in risk
    assert "coverage_metrics" in quality
    assert quality["draft_summary"]["draft_count"] == draft_count
    assert quality["draft_summary"]["draft_ticket_count"] == quality_draft_tickets
    assert quality["final_response_summary"]["final_response_ticket_count"] == final_response_tickets
    assert quality["safety_summary"]["safety_check_count"] == safety_check_count


def test_weekly_report_reads_db_and_contains_all_ticket_analysis_columns() -> None:
    _skip_if_no_db_password()

    result = run_weekly_report_workflow(7)
    report = result["report"]

    assert "summary" in report
    assert "column_insights" in report
    assert "analysis_rows" in report

    rows = report["analysis_rows"]
    if not rows:
        return

    required_columns = {
        "analysis_id",
        "ticket_id",
        "category",
        "responder_type",
        "enriched_query",
        "risk_level",
        "sentiment",
        "routing_target",
        "summary",
        "analyzed_at",
    }
    first_row = rows[0]
    assert required_columns.issubset(first_row.keys())
