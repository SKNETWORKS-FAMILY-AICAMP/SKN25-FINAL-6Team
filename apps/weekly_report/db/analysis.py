"""분석 행 DB 조회 — ticket_analysis + qa_ticket + insight 조인."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from db.connection import _fetch_all


def _latest_insight_join_sql() -> str:
    """티켓당 가장 최근 insight 행 하나를 가져오는 LATERAL JOIN SQL 조각을 반환한다.

    같은 ticket_id에 insight가 여러 개 있을 수 있으므로 LATERAL + LIMIT 1로 최신 1건만 선택한다.
    insight가 없는 티켓도 포함해야 하므로 LEFT JOIN LATERAL ... ON TRUE 패턴을 사용한다.
    """
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
            -- 가장 최근 insight를 우선으로 하되, inquiry_created_at이 같으면 insight_id 내림차순
            ORDER BY i.inquiry_created_at DESC NULLS LAST, i.insight_id DESC
            LIMIT 1
        ) latest_insight ON TRUE
    """


def fetch_analysis_rows(window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    """window 기간 내 분석 행을 최신순으로 모두 조회한다.

    - analyzed_at 기준으로 기간을 필터링한다 (inquiry_created_at 기준이 아님).
    - community_users는 닉네임 표시용으로 LEFT JOIN — 가입 전 문의나 익명 문의도 포함된다.
    - 반환 리스트는 build/payload.py, ai/row_interpret.py 등에서 직접 사용한다.
    """
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
        -- analyzed_at이 동일한 행은 analysis_id 역순으로 정렬해 재현 가능한 순서를 보장한다.
        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    """
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_all(cur, sql, (window_start, window_end))
