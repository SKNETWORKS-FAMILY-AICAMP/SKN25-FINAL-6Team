"""Analysis row queries for the weekly report."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from db.connection import _fetch_all
from weekly_report_langfuse import link_weekly_report_trace


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


@observe_if_enabled(
    name="weekly_report_fetch_analysis_rows",
    as_type="generation",
    tags=["weekly-report", "feature:data-fetch", "source:analysis"],
)
def fetch_analysis_rows(window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
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
        WHERE t.inquiry_created_at >= %s
          AND t.inquiry_created_at < %s
        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    """
    link_weekly_report_trace(
        {"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        tags=["weekly-report", "feature:data-fetch", "source:analysis"],
        input_payload={"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
    )
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(cur, sql, (window_start, window_end))
    link_weekly_report_trace(
        {"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        tags=["weekly-report", "feature:data-fetch", "source:analysis"],
        output_payload={"current_rows_count": len(rows)},
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        current_rows_count=len(rows),
    )
    return rows
