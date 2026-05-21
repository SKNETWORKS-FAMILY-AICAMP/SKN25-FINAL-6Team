"""LangGraph nodes and calculation helpers for the dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Literal, cast

from psycopg.rows import dict_row

from src.common.db.connection import db_connection

from .state import DashboardState


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[DashboardState], StateUpdate]
Route = Literal["overview", "risk", "quality", "all"]


def _state(state: DashboardState | dict[str, Any]) -> DashboardState:
    return DashboardState.model_validate(state)


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _rate(numerator: int | float | None, denominator: int | float | None) -> float:
    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


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
            SELECT d.draft_id, d.created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
    """


def _latest_response_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT fr.response_id, fr.created_at, fr.safety_action
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) latest_response ON TRUE
    """


def _window_start(current: DashboardState) -> datetime:
    if current.window_start is None:
        raise ValueError("dashboard workflow requires window_start")
    return current.window_start


def load_window_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    days = max(1, min(int(current.days), 365))
    return {"days": days, "window_start": datetime.now() - timedelta(days=days)}


def fetch_overview_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    window_start = _window_start(current)
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
                    SELECT ticket_id FROM answer_draft d WHERE d.ticket_id = t.ticket_id LIMIT 1
                ) d ON TRUE
                LEFT JOIN LATERAL (
                    SELECT ticket_id FROM ticket_analysis a WHERE a.ticket_id = t.ticket_id LIMIT 1
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
    return {
        "overview": {
            "window_days": current.days,
            "raw_counts": counts,
            "raw_response_metrics": response_metrics,
            "source_distribution": source_distribution,
            "status_distribution": status_distribution,
            "routing_distribution": routing_distribution,
            "recent_tickets": recent_tickets,
        }
    }


def compute_overview_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    overview = dict(current.overview)
    counts = overview.pop("raw_counts", {})
    response_metrics = overview.pop("raw_response_metrics", {})
    ticket_count = int(counts.get("total_tickets") or 0)
    responded_tickets = int(response_metrics.get("responded_tickets") or 0)
    draft_tickets = int(response_metrics.get("draft_tickets") or 0)
    analyzed_tickets = int(response_metrics.get("analyzed_tickets") or 0)
    overview.update(
        {
            "window_days": current.days,
            "ticket_counts": {
                "total": ticket_count,
                "pending": int(counts.get("pending_tickets") or 0),
                "closed": int(counts.get("closed_tickets") or 0),
                "today": int(counts.get("today_tickets") or 0),
            },
            "response_metrics": {
                "response_rate": _rate(responded_tickets, ticket_count),
                "draft_coverage_rate": _rate(draft_tickets, ticket_count),
                "analysis_coverage_rate": _rate(analyzed_tickets, ticket_count),
                "avg_response_latency_minutes": response_metrics.get("avg_response_latency_minutes"),
            },
        }
    )
    return {"overview": overview}


def fetch_risk_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    if current.section == "overview":
        return {}
    window_start = _window_start(current)
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
                    SELECT i.risk_level, i.pattern_risk_level
                    FROM insight i
                    WHERE i.ticket_id = t.ticket_id
                    ORDER BY i.inquiry_created_at DESC NULLS LAST, i.insight_id DESC
                    LIMIT 1
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
    return {
        "risk": {
            "window_days": current.days,
            "analysis_risk_distribution": analysis_risk_distribution,
            "sentiment_distribution": sentiment_distribution,
            "insight_risk_distribution": insight_risk_distribution,
            "pattern_risk_distribution": pattern_risk_distribution,
            "safety_score_summary": safety_score_summary,
            "high_risk_tickets": high_risk_tickets,
        }
    }


def compute_risk_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    if current.section == "overview":
        return {}
    safety = dict(current.risk.get("safety_score_summary") or {})
    risk = dict(current.risk)
    risk["safety_alerts"] = {
        "high_hallucination": (safety.get("avg_hallucination_score") or 0) >= 0.7,
        "high_toxicity": (safety.get("avg_toxicity_score") or 0) >= 0.7,
        "high_policy_violation": (safety.get("avg_policy_violation_score") or 0) >= 0.7,
        "low_factuality": safety.get("avg_factuality_score") is not None
        and safety.get("avg_factuality_score") <= 0.3,
    }
    return {"risk": risk}


def fetch_quality_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    if current.section in ("overview", "risk"):
        return {}
    window_start = _window_start(current)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket_summary = _fetch_one(
                cur,
                """
                SELECT COUNT(*) AS ticket_count
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            draft_summary = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(DISTINCT d.draft_id) AS draft_count,
                    COUNT(DISTINCT d.ticket_id) AS draft_ticket_count,
                    COUNT(DISTINCT CASE
                        WHEN EXISTS (SELECT 1 FROM evidence_docs e WHERE e.draft_id = d.draft_id)
                        THEN d.draft_id
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
                """
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
    return {
        "quality": {
            "window_days": current.days,
            "ticket_summary": ticket_summary,
            "draft_summary": draft_summary,
            "evidence_summary": evidence_summary,
            "safety_summary": safety_summary,
            "final_response_summary": final_response_summary,
            "notification_summary": notification_summary,
            "quality_candidates": quality_candidates,
        }
    }


def compute_quality_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    if current.section in ("overview", "risk"):
        return {}
    draft = current.quality.get("draft_summary") or {}
    final_response = current.quality.get("final_response_summary") or {}
    ticket_total = int(
        (current.overview.get("ticket_counts") or {}).get("total")
        or (current.quality.get("ticket_summary") or {}).get("ticket_count")
        or 0
    )
    quality = dict(current.quality)
    quality["coverage_metrics"] = {
        "draft_ticket_rate": _rate(draft.get("draft_ticket_count"), ticket_total),
        "evidence_attachment_rate": _rate(draft.get("evidence_linked_drafts"), draft.get("draft_count")),
        "final_response_ticket_rate": _rate(final_response.get("final_response_ticket_count"), ticket_total),
    }
    return {"quality": quality}


def route_after_window(state: DashboardState) -> Route:
    current = _state(state)
    return cast(Route, current.section)


NODE_FUNCTIONS: dict[str, NodeHandler] = {
    "load_window_node": load_window_node,
    "fetch_overview_node": fetch_overview_node,
    "compute_overview_node": compute_overview_node,
    "fetch_risk_node": fetch_risk_node,
    "compute_risk_node": compute_risk_node,
    "fetch_quality_node": fetch_quality_node,
    "compute_quality_node": compute_quality_node,
}
