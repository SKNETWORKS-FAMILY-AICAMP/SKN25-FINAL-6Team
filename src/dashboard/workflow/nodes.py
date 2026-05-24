"""Pipeline steps and calculation helpers for the dashboard."""

from __future__ import annotations

from typing import Any, Callable, Literal, cast

from psycopg.rows import dict_row

from src.common.db.connection import db_connection
from src.dashboard.util import (
    build_overview_payload,
    build_quality_payload,
    build_risk_payload,
    build_window,
    clamp_days,
)

from .state import DashboardState


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[DashboardState], StateUpdate]
Route = Literal["overview", "risk", "quality", "all"]
NextAfterSection = Literal["all", "stop"]


def _state(state: DashboardState | dict[str, Any]) -> DashboardState:
    return DashboardState.model_validate(state)


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


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


def _latest_safety_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                s.safety_id,
                s.hallucination_score,
                s.toxicity_score,
                s.policy_violation_score,
                s.factuality_score,
                s.checked_at,
                s.safety_action,
                s.safety_reason
            FROM safety_results s
            WHERE s.draft_id = d.draft_id
            ORDER BY s.checked_at DESC NULLS LAST, s.safety_id DESC
            LIMIT 1
        ) latest_safety ON TRUE
    """


def _window_start(current: DashboardState) -> Any:
    if current.window_start is None:
        raise ValueError("dashboard workflow requires window_start")
    return current.window_start


def _window_end(current: DashboardState) -> Any:
    if current.window_end is None:
        raise ValueError("dashboard workflow requires window_end")
    return current.window_end


def load_window_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    days = clamp_days(current.days)
    # Downstream SQL nodes all read the same computed window from state.
    window = build_window(days)
    return {
        "days": window["days"],
        "window_start": window["window_start"],
        "window_end": window["window_end"],
    }


def fetch_overview_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    window_start = _window_start(current)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            raw_counts = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(*) AS total_tickets,
                    COUNT(*) FILTER (WHERE t.status = 'pending') AS pending_tickets,
                    COUNT(*) FILTER (WHERE t.status = 'closed') AS closed_tickets,
                    COUNT(*) FILTER (
                        WHERE t.inquiry_created_at >= CURRENT_DATE
                          AND t.inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'
                    ) AS today_tickets,
                    COUNT(*) FILTER (
                        WHERE t.status = 'pending'
                          AND t.inquiry_created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    ) AS old_pending_count
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                """,
                (window_start,),
            ) or {}
            response_metrics = _fetch_one(
                cur,
                f"""
                SELECT
                    COUNT(DISTINCT t.ticket_id) FILTER (WHERE latest_response.response_id IS NOT NULL) AS responded_tickets,
                    COUNT(DISTINCT d.ticket_id) AS draft_tickets,
                    COUNT(DISTINCT a.ticket_id) AS analyzed_tickets,
                    AVG(EXTRACT(EPOCH FROM (latest_response.created_at - t.inquiry_created_at)) / 60.0)
                        FILTER (
                            WHERE latest_response.created_at IS NOT NULL
                              AND t.inquiry_created_at IS NOT NULL
                        ) AS avg_response_latency_minutes
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT response_id, created_at
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
                    latest_analysis.sentiment,
                    latest_analysis.routing_target,
                    latest_analysis.analysis_id AS latest_analysis_id,
                    latest_draft.draft_id AS latest_draft_id,
                    latest_response.response_id AS latest_response_id,
                    latest_response.created_at AS latest_response_created_at
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                {_latest_analysis_join_sql()}
                {_latest_draft_join_sql()}
                {_latest_response_join_sql()}
                WHERE t.inquiry_created_at >= %s
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT 50
                """,
                (window_start,),
            )
    return {
        "overview": {
            "window": {
                "days": current.days,
                "window_start": _window_start(current),
                "window_end": _window_end(current),
            },
            "raw_counts": raw_counts,
            "response_metrics": response_metrics,
            "source_distribution": source_distribution,
            "status_distribution": status_distribution,
            "routing_distribution": routing_distribution,
            "recent_tickets": recent_tickets,
        }
    }
def _build_overview_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return build_overview_payload(
        window=raw["window"],
        raw_counts=raw["raw_counts"],
        response_metrics=raw["response_metrics"],
        source_distribution=raw["source_distribution"],
        status_distribution=raw["status_distribution"],
        routing_distribution=raw["routing_distribution"],
        recent_tickets=raw["recent_tickets"],
    )


def compute_overview_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    return {"overview": _build_overview_payload(current.overview)}


def fetch_risk_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
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
                    latest_analysis.analysis_id,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.sentiment,
                    latest_analysis.routing_target,
                    latest_insight.pattern_risk_level
                FROM qa_ticket t
                {_latest_analysis_join_sql()}
                LEFT JOIN LATERAL (
                    SELECT
                        i.risk_level,
                        i.pattern_risk_level
                    FROM insight i
                    WHERE i.ticket_id = t.ticket_id
                    ORDER BY i.inquiry_created_at DESC NULLS LAST, i.insight_id DESC
                    LIMIT 1
                ) latest_insight ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND (
                    LOWER(COALESCE(latest_analysis.risk_level, '')) IN ('high', 'critical')
                    OR LOWER(COALESCE(latest_insight.pattern_risk_level, '')) IN ('high', 'critical')
                    OR LOWER(COALESCE(latest_analysis.routing_target, '')) = 'human_review'
                  )
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )
            safety_breach_candidates = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.inquiry_created_at,
                    d.draft_id,
                    latest_safety.hallucination_score,
                    latest_safety.toxicity_score,
                    latest_safety.policy_violation_score,
                    latest_safety.factuality_score,
                    latest_safety.safety_action,
                    latest_safety.checked_at
                FROM qa_ticket t
                JOIN answer_draft d ON d.ticket_id = t.ticket_id
                {_latest_safety_join_sql()}
                WHERE t.inquiry_created_at >= %s
                  AND (
                    COALESCE(latest_safety.factuality_score, 1) <= 0.3
                    OR COALESCE(latest_safety.hallucination_score, 0) >= 0.7
                    OR COALESCE(latest_safety.policy_violation_score, 0) >= 0.7
                    OR COALESCE(latest_safety.toxicity_score, 0) >= 0.7
                  )
                ORDER BY
                    COALESCE(latest_safety.factuality_score, 1) ASC,
                    COALESCE(latest_safety.hallucination_score, 0) DESC,
                    d.created_at DESC NULLS LAST,
                    t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )
    return {
        "risk": {
            "window": {
                "days": current.days,
                "window_start": _window_start(current),
                "window_end": _window_end(current),
            },
            "analysis_risk_distribution": analysis_risk_distribution,
            "sentiment_distribution": sentiment_distribution,
            "insight_risk_distribution": insight_risk_distribution,
            "pattern_risk_distribution": pattern_risk_distribution,
            "safety_score_summary": safety_score_summary,
            "high_risk_tickets": high_risk_tickets,
            "safety_breach_candidates": safety_breach_candidates,
        }
    }
def _build_risk_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return build_risk_payload(
        window=raw["window"],
        analysis_risk_distribution=raw["analysis_risk_distribution"],
        sentiment_distribution=raw["sentiment_distribution"],
        insight_risk_distribution=raw["insight_risk_distribution"],
        pattern_risk_distribution=raw["pattern_risk_distribution"],
        safety_score_summary=raw["safety_score_summary"],
        high_risk_tickets=raw["high_risk_tickets"],
        safety_breach_candidates=raw["safety_breach_candidates"],
    )


def compute_risk_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    return {"risk": _build_risk_payload(current.risk)}


def fetch_quality_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
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
                        FILTER (
                            WHERE d.created_at IS NOT NULL
                              AND t.inquiry_created_at IS NOT NULL
                        ) AS avg_draft_latency_minutes
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
                        FILTER (
                            WHERE fr.created_at IS NOT NULL
                              AND t.inquiry_created_at IS NOT NULL
                        ) AS avg_final_latency_minutes
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
                    latest_safety.hallucination_score,
                    latest_safety.toxicity_score,
                    latest_safety.policy_violation_score,
                    latest_safety.factuality_score,
                    latest_safety.safety_action
                FROM qa_ticket t
                JOIN answer_draft d ON d.ticket_id = t.ticket_id
                {_latest_safety_join_sql()}
                WHERE t.inquiry_created_at >= %s
                  AND (
                    COALESCE(latest_safety.factuality_score, 1) <= 0.3
                    OR COALESCE(latest_safety.hallucination_score, 0) >= 0.7
                  )
                ORDER BY
                    COALESCE(latest_safety.factuality_score, 1) ASC,
                    COALESCE(latest_safety.hallucination_score, 0) DESC,
                    d.created_at DESC NULLS LAST,
                    t.ticket_id DESC
                LIMIT 25
                """,
                (window_start,),
            )
            notification_failures = _fetch_all(
                cur,
                """
                SELECT
                    n.notification_id,
                    n.ticket_id,
                    t.title,
                    n.channel,
                    n.status,
                    n.error_category,
                    n.error_message,
                    n.sent_at
                FROM notification_logs n
                JOIN qa_ticket t ON t.ticket_id = n.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND LOWER(COALESCE(n.status, '')) IN ('failed', 'error')
                ORDER BY n.sent_at DESC NULLS LAST, n.notification_id DESC
                LIMIT 25
                """,
                (window_start,),
            )
    return {
        "quality": {
            "window": {
                "days": current.days,
                "window_start": _window_start(current),
                "window_end": _window_end(current),
            },
            "ticket_summary": ticket_summary,
            "draft_summary": draft_summary,
            "evidence_summary": evidence_summary,
            "safety_summary": safety_summary,
            "final_response_summary": final_response_summary,
            "notification_summary": notification_summary,
            "quality_candidates": quality_candidates,
            "notification_failures": notification_failures,
        }
    }
def _build_quality_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return build_quality_payload(
        window=raw["window"],
        ticket_summary=raw["ticket_summary"],
        draft_summary=raw["draft_summary"],
        evidence_summary=raw["evidence_summary"],
        safety_summary=raw["safety_summary"],
        final_response_summary=raw["final_response_summary"],
        notification_summary=raw["notification_summary"],
        quality_candidates=raw["quality_candidates"],
        notification_failures=raw["notification_failures"],
    )


def compute_quality_node(state: DashboardState) -> StateUpdate:
    current = _state(state)
    return {"quality": _build_quality_payload(current.quality)}


def route_after_window(state: DashboardState) -> Route:
    current = _state(state)
    return cast(Route, current.section)


def route_after_overview(state: DashboardState) -> NextAfterSection:
    current = _state(state)
    return "all" if current.section == "all" else "stop"


def route_after_risk(state: DashboardState) -> NextAfterSection:
    current = _state(state)
    return "all" if current.section == "all" else "stop"


NODE_FUNCTIONS: dict[str, NodeHandler] = {
    "load_window_node": load_window_node,
    "fetch_overview_node": fetch_overview_node,
    "compute_overview_node": compute_overview_node,
    "fetch_risk_node": fetch_risk_node,
    "compute_risk_node": compute_risk_node,
    "fetch_quality_node": fetch_quality_node,
    "compute_quality_node": compute_quality_node,
}
