"""FastAPI endpoints for the dashboard summary pages."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from src.common.db.connection import db_connection


app = FastAPI(title="Dashboard API", version="1.0.0")


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    return _row_to_dict(cur.fetchone())


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _window_start(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)


def _latest_analysis_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                a.analysis_id,
                a.category,
                a.responder_type,
                a.risk_level,
                a.sentiment,
                a.routing_target,
                a.summary,
                a.analyzed_at
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
            LIMIT 1
        ) latest_analysis ON TRUE
    """


def _latest_draft_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                d.draft_id,
                d.created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
    """


def _latest_response_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                fr.response_id,
                fr.created_at,
                fr.safety_action
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) latest_response ON TRUE
    """


def _latest_safety_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                sr.draft_id,
                sr.hallucination_score,
                sr.toxicity_score,
                sr.policy_violation_score,
                sr.factuality_score,
                sr.safety_action,
                sr.checked_at
            FROM safety_results sr
            JOIN answer_draft d ON d.draft_id = sr.draft_id
            WHERE d.ticket_id = t.ticket_id
            ORDER BY sr.checked_at DESC NULLS LAST, sr.safety_id DESC
            LIMIT 1
        ) latest_safety ON TRUE
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/summary/overview")
def summary_overview(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    window_start = _window_start(days)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            counts = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(*) AS total_tickets,
                    COUNT(*) FILTER (WHERE t.status = 'pending') AS pending_tickets,
                    COUNT(*) FILTER (WHERE t.status = 'closed') AS closed_tickets,
                    COUNT(*) FILTER (
                        WHERE t.inquiry_created_at >= CURRENT_DATE
                        AND t.inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'
                    ) AS today_tickets
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}

            response_metrics = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT t.ticket_id) FILTER (WHERE fr.response_id IS NOT NULL) AS responded_tickets,
                    COUNT(DISTINCT t.ticket_id) AS ticket_count,
                    AVG(EXTRACT(EPOCH FROM (fr.created_at - t.inquiry_created_at)) / 60.0)
                        FILTER (WHERE fr.created_at IS NOT NULL AND t.inquiry_created_at IS NOT NULL)
                        AS avg_response_latency_minutes,
                    COUNT(DISTINCT d.ticket_id) AS draft_tickets,
                    COUNT(DISTINCT a.ticket_id) AS analyzed_tickets
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT response_id, created_at
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
            ) or {}

            source_distribution = _fetch_all(
                cur,
                """
                SELECT COALESCE(t.source_type, 'unknown') AS label, COUNT(*) AS value
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            status_distribution = _fetch_all(
                cur,
                """
                SELECT COALESCE(t.status, 'unknown') AS label, COUNT(*) AS value
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            routing_distribution = _fetch_all(
                cur,
                f"""
                SELECT COALESCE(latest_analysis.routing_target, 'unknown') AS label, COUNT(*) AS value
                FROM qa_ticket t
                {_latest_analysis_join_sql()}
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            recent_tickets = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.source_type,
                    t.inquiry_created_at,
                    u.nickname,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.routing_target,
                    latest_draft.draft_id,
                    latest_response.response_id,
                    latest_response.created_at AS response_created_at
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                {_latest_analysis_join_sql()}
                {_latest_draft_join_sql()}
                {_latest_response_join_sql()}
                WHERE t.inquiry_created_at >= %s
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )

    ticket_count = int(counts.get("total_tickets") or 0)
    responded_tickets = int(response_metrics.get("responded_tickets") or 0)
    draft_tickets = int(response_metrics.get("draft_tickets") or 0)
    analyzed_tickets = int(response_metrics.get("analyzed_tickets") or 0)

    return jsonable_encoder(
        {
            "window_days": days,
            "ticket_counts": {
                "total": ticket_count,
                "pending": int(counts.get("pending_tickets") or 0),
                "closed": int(counts.get("closed_tickets") or 0),
                "today": int(counts.get("today_tickets") or 0),
            },
            "response_metrics": {
                "response_rate": responded_tickets / ticket_count if ticket_count else 0,
                "draft_coverage_rate": draft_tickets / ticket_count if ticket_count else 0,
                "analysis_coverage_rate": analyzed_tickets / ticket_count if ticket_count else 0,
                "avg_response_latency_minutes": response_metrics.get("avg_response_latency_minutes"),
            },
            "source_distribution": source_distribution,
            "status_distribution": status_distribution,
            "routing_distribution": routing_distribution,
            "recent_tickets": recent_tickets,
        }
    )


@app.get("/summary/risk")
def summary_risk(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    window_start = _window_start(days)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            analysis_risk_distribution = _fetch_all(
                cur,
                f"""
                SELECT COALESCE(latest_analysis.risk_level, 'unknown') AS label, COUNT(*) AS value
                FROM qa_ticket t
                {_latest_analysis_join_sql()}
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            sentiment_distribution = _fetch_all(
                cur,
                f"""
                SELECT COALESCE(latest_analysis.sentiment, 'unknown') AS label, COUNT(*) AS value
                FROM qa_ticket t
                {_latest_analysis_join_sql()}
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            insight_risk_distribution = _fetch_all(
                cur,
                """
                SELECT COALESCE(i.risk_level, 'unknown') AS label, COUNT(*) AS value
                FROM insight i
                JOIN qa_ticket t ON t.ticket_id = i.ticket_id
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            pattern_risk_distribution = _fetch_all(
                cur,
                """
                SELECT COALESCE(i.pattern_risk_level, 'unknown') AS label, COUNT(*) AS value
                FROM insight i
                JOIN qa_ticket t ON t.ticket_id = i.ticket_id
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            safety_score_summary = _fetch_one(
                cur,
                """
                SELECT
                    AVG(s.hallucination_score) AS avg_hallucination_score,
                    AVG(s.toxicity_score) AS avg_toxicity_score,
                    AVG(s.policy_violation_score) AS avg_policy_violation_score,
                    AVG(s.factuality_score) AS avg_factuality_score,
                    COUNT(*) AS safety_check_count
                FROM safety_results s
                JOIN answer_draft d ON d.draft_id = s.draft_id
                JOIN qa_ticket t ON t.ticket_id = d.ticket_id
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            high_risk_tickets = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.inquiry_created_at,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.sentiment,
                    latest_analysis.routing_target,
                    latest_insight.pattern_risk_level
                FROM qa_ticket t
                {_latest_analysis_join_sql()}
                LEFT JOIN LATERAL (
                    SELECT DISTINCT ON (i.ticket_id)
                        risk_level,
                        pattern_risk_level
                    FROM insight i
                    WHERE i.ticket_id = t.ticket_id
                    ORDER BY i.ticket_id, i.inquiry_created_at DESC NULLS LAST, i.insight_id DESC
                ) latest_insight ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND (
                    LOWER(COALESCE(latest_analysis.risk_level, '')) IN ('high', 'critical')
                    OR LOWER(COALESCE(latest_insight.pattern_risk_level, '')) IN ('high', 'critical')
                  )
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )

    return jsonable_encoder(
        {
            "window_days": days,
            "analysis_risk_distribution": analysis_risk_distribution,
            "sentiment_distribution": sentiment_distribution,
            "insight_risk_distribution": insight_risk_distribution,
            "pattern_risk_distribution": pattern_risk_distribution,
            "safety_score_summary": safety_score_summary,
            "high_risk_tickets": high_risk_tickets,
        }
    )


@app.get("/summary/quality")
def summary_quality(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    window_start = _window_start(days)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft_summary = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT d.draft_id) AS draft_count,
                    COUNT(DISTINCT d.ticket_id) AS draft_ticket_count,
                    COUNT(DISTINCT CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM evidence_docs e
                            WHERE e.draft_id = d.draft_id
                        ) THEN d.draft_id
                    END) AS evidence_linked_drafts,
                    AVG(EXTRACT(EPOCH FROM (d.created_at - t.inquiry_created_at)) / 60.0)
                        FILTER (WHERE d.created_at IS NOT NULL AND t.inquiry_created_at IS NOT NULL)
                        AS avg_draft_latency_minutes
                FROM qa_ticket t
                LEFT JOIN answer_draft d ON d.ticket_id = t.ticket_id
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            evidence_summary = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(*) AS evidence_count,
                    AVG(e.relevance_score) AS avg_relevance_score,
                    AVG(e.retrieval_rank) AS avg_retrieval_rank
                FROM evidence_docs e
                JOIN answer_draft d ON d.draft_id = e.draft_id
                JOIN qa_ticket t ON t.ticket_id = d.ticket_id
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            safety_summary = _fetch_one(
                cur,
                """
                SELECT
                    AVG(s.hallucination_score) AS avg_hallucination_score,
                    AVG(s.toxicity_score) AS avg_toxicity_score,
                    AVG(s.policy_violation_score) AS avg_policy_violation_score,
                    AVG(s.factuality_score) AS avg_factuality_score,
                    COUNT(*) AS safety_check_count
                FROM safety_results s
                JOIN answer_draft d ON d.draft_id = s.draft_id
                JOIN qa_ticket t ON t.ticket_id = d.ticket_id
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            final_response_summary = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT fr.response_id) AS final_response_count,
                    COUNT(DISTINCT fr.ticket_id) AS final_response_ticket_count,
                    AVG(EXTRACT(EPOCH FROM (fr.created_at - t.inquiry_created_at)) / 60.0)
                        FILTER (WHERE fr.created_at IS NOT NULL AND t.inquiry_created_at IS NOT NULL)
                        AS avg_final_latency_minutes
                FROM qa_ticket t
                LEFT JOIN final_response fr ON fr.ticket_id = t.ticket_id
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            notification_summary = _fetch_all(
                cur,
                """
                SELECT COALESCE(n.status, 'unknown') AS label, COUNT(*) AS value
                FROM notification_logs n
                JOIN qa_ticket t ON t.ticket_id = n.ticket_id
                WHERE t.inquiry_created_at >= %s
                GROUP BY 1
                ORDER BY value DESC, label ASC
                """,
                (window_start,),
            )
            quality_candidates = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.inquiry_created_at,
                    d.draft_id,
                    s.hallucination_score,
                    s.toxicity_score,
                    s.policy_violation_score,
                    s.factuality_score,
                    s.safety_action
                FROM qa_ticket t
                JOIN answer_draft d ON d.ticket_id = t.ticket_id
                LEFT JOIN LATERAL (
                    SELECT
                        s.hallucination_score,
                        s.toxicity_score,
                        s.policy_violation_score,
                        s.factuality_score,
                        s.safety_action
                    FROM safety_results s
                    WHERE s.draft_id = d.draft_id
                    ORDER BY s.checked_at DESC NULLS LAST, s.safety_id DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE t.inquiry_created_at >= %s
                ORDER BY
                    COALESCE(s.factuality_score, 1) ASC,
                    COALESCE(s.hallucination_score, 0) DESC,
                    d.created_at DESC NULLS LAST,
                    t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )

    return jsonable_encoder(
        {
            "window_days": days,
            "draft_summary": draft_summary,
            "evidence_summary": evidence_summary,
            "safety_summary": safety_summary,
            "final_response_summary": final_response_summary,
            "notification_summary": notification_summary,
            "quality_candidates": quality_candidates,
        }
    )


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            where_sql = "WHERE 1 = 1"
            params: list[Any] = []
            if status:
                where_sql += " AND t.status = %s"
                params.append(status)
            params.append(limit)
            rows = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.source_type,
                    t.inquiry_created_at,
                    u.nickname,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.routing_target,
                    latest_draft.draft_id,
                    latest_response.response_id,
                    latest_response.created_at AS response_created_at
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                {_latest_analysis_join_sql()}
                {_latest_draft_join_sql()}
                {_latest_response_join_sql()}
                {where_sql}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
    return jsonable_encoder(rows)


@app.get("/tickets/{ticket_id}")
def get_ticket_detail(ticket_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket = _fetch_one(
                cur,
                """
                SELECT
                    t.*,
                    u.email,
                    u.nickname,
                    u.user_status,
                    u.last_login_at,
                    a.game_name,
                    a.uid,
                    a.server_region,
                    a.progression_level,
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            if ticket is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")

            analyses = _fetch_all(
                cur,
                """
                SELECT *
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                """,
                (ticket_id,),
            )
            drafts = _fetch_all(
                cur,
                """
                SELECT *
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                """,
                (ticket_id,),
            )
            draft_ids = [draft["draft_id"] for draft in drafts]
            evidence_docs: list[dict[str, Any]] = []
            safety_results: list[dict[str, Any]] = []
            if draft_ids:
                evidence_docs = _fetch_all(
                    cur,
                    """
                    SELECT *
                    FROM evidence_docs
                    WHERE draft_id = ANY(%s)
                    ORDER BY draft_id DESC, retrieval_rank ASC
                    """,
                    (draft_ids,),
                )
                safety_results = _fetch_all(
                    cur,
                    """
                    SELECT *
                    FROM safety_results
                    WHERE draft_id = ANY(%s)
                    ORDER BY checked_at DESC NULLS LAST, safety_id DESC
                    """,
                    (draft_ids,),
                )
            final_responses = _fetch_all(
                cur,
                """
                SELECT *
                FROM final_response
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, response_id DESC
                """,
                (ticket_id,),
            )
            notifications = _fetch_all(
                cur,
                """
                SELECT *
                FROM notification_logs
                WHERE ticket_id = %s
                ORDER BY sent_at DESC NULLS LAST, notification_id DESC
                """,
                (ticket_id,),
            )
    return jsonable_encoder(
        {
            "ticket": ticket,
            "analyses": analyses,
            "drafts": drafts,
            "evidence_docs": evidence_docs,
            "safety_results": safety_results,
            "final_responses": final_responses,
            "notifications": notifications,
        }
    )
