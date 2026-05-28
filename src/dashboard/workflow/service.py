"""Dashboard workflow built from plain classes and functions."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.common.db.connection import db_connection
from src.dashboard.util import (
    build_overview_payload,
    build_quality_payload,
    build_risk_payload,
    build_window,
    clamp_days,
    generate_dashboard_interpretation,
    rate,
)

from .state import DashboardSection


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
                s.safety_reason,
                s.retry_count
            FROM safety_results s
            WHERE s.draft_id = d.draft_id
            ORDER BY s.checked_at DESC NULLS LAST, s.safety_id DESC
            LIMIT 1
        ) latest_safety ON TRUE
    """


def _distribution_rows(rows: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "unknown").strip() or "unknown"
        counts[label] = counts.get(label, 0) + 1
    return [
        {"label": label, "value": value}
        for label, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _window(days: int) -> dict[str, Any]:
    return build_window(clamp_days(days))


def _apply_ai(page: DashboardSection, payload: dict[str, Any]) -> dict[str, Any]:
    payload["ai_interpretation"] = generate_dashboard_interpretation(page, payload)
    return payload


def _overview_summary(window: dict[str, Any], *, connection_factory: Any = db_connection) -> dict[str, Any]:
    with connection_factory() as conn:
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
                (window["window_start"],),
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
                        ) AS avg_response_latency_minutes,
                    COUNT(*) FILTER (
                        WHERE latest_response.created_at IS NOT NULL
                          AND latest_response.created_at <= t.inquiry_created_at + INTERVAL '24 hours'
                    ) AS responded_within_24h,
                    COUNT(*) FILTER (
                        WHERE latest_response.response_id IS NULL
                    ) AS unanswered_tickets
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                    latest_analysis.responder_type,
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
                (window["window_start"],),
            )

    payload = build_overview_payload(
        window=window,
        raw_counts=raw_counts,
        response_metrics=response_metrics,
        source_distribution=source_distribution,
        status_distribution=status_distribution,
        routing_distribution=routing_distribution,
        recent_tickets=recent_tickets,
    )
    total = int(payload["ticket_counts"]["total"] or 0)
    pending_priority_rows = [row for row in recent_tickets if str(row.get("status") or "").lower() == "pending"]
    payload["category_distribution"] = _distribution_rows(recent_tickets, key="category")
    payload["responder_distribution"] = _distribution_rows(recent_tickets, key="responder_type")
    payload["sla_metrics"] = {
        "responded_within_24h_rate": rate(response_metrics.get("responded_within_24h"), total),
        "unanswered_rate": rate(response_metrics.get("unanswered_tickets"), total),
        "avg_response_latency_minutes": response_metrics.get("avg_response_latency_minutes"),
    }
    payload["backlog_metrics"] = {
        "pending_tickets": payload["ticket_counts"]["pending"],
        "old_pending_count": payload["old_pending_count"],
        "urgent_unanswered_count": sum(
            1 for row in pending_priority_rows if str(row.get("routing_target") or "").lower() == "urgent_alert"
        ),
        "human_review_backlog_count": sum(
            1 for row in pending_priority_rows if str(row.get("routing_target") or "").lower() == "human_review"
        ),
    }
    payload["priority_tickets"] = [
        {
            **row,
            "queue_reason": ", ".join(
                reason
                for reason, enabled in [
                    ("high_risk", str(row.get("risk_level") or "").lower() in {"high", "critical"}),
                    ("negative_sentiment", str(row.get("sentiment") or "").lower() in {"negative", "very_negative"}),
                    ("needs_human_review", str(row.get("routing_target") or "").lower() == "human_review"),
                    ("urgent_alert", str(row.get("routing_target") or "").lower() == "urgent_alert"),
                ]
                if enabled
            ) or "pending"
        }
        for row in pending_priority_rows[:12]
    ]
    return _apply_ai("overview", payload)


def _risk_summary(window: dict[str, Any], *, connection_factory: Any = db_connection) -> dict[str, Any]:
    with connection_factory() as conn:
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
            ) or {}
            high_risk_tickets = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.source_type,
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
                (window["window_start"],),
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
                    latest_safety.checked_at,
                    latest_safety.retry_count
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
                (window["window_start"],),
            )

    payload = build_risk_payload(
        window=window,
        analysis_risk_distribution=analysis_risk_distribution,
        sentiment_distribution=sentiment_distribution,
        insight_risk_distribution=insight_risk_distribution,
        pattern_risk_distribution=pattern_risk_distribution,
        safety_score_summary=safety_score_summary,
        high_risk_tickets=high_risk_tickets,
        safety_breach_candidates=safety_breach_candidates,
    )
    payload["risk_summary"] = {
        "high_risk_count": sum(
            1 for row in high_risk_tickets if str(row.get("risk_level") or "").lower() in {"high", "critical"}
        ),
        "critical_risk_count": sum(1 for row in high_risk_tickets if str(row.get("risk_level") or "").lower() == "critical"),
        "human_review_count": sum(
            1 for row in high_risk_tickets if str(row.get("routing_target") or "").lower() == "human_review"
        ),
        "negative_sentiment_count": sum(
            1 for row in high_risk_tickets if str(row.get("sentiment") or "").lower() in {"negative", "very_negative"}
        ),
    }
    payload["risk_hotspots"] = {
        "category_distribution": _distribution_rows(high_risk_tickets, key="category"),
        "source_distribution": _distribution_rows(high_risk_tickets, key="source_type"),
    }
    payload["escalation_queue"] = [
        {
            **row,
            "escalation_reason": ", ".join(
                reason
                for reason, enabled in [
                    ("critical_risk", str(row.get("risk_level") or "").lower() == "critical"),
                    ("human_review", str(row.get("routing_target") or "").lower() == "human_review"),
                    ("negative_sentiment", str(row.get("sentiment") or "").lower() in {"negative", "very_negative"}),
                    ("pattern_risk", str(row.get("pattern_risk_level") or "").lower() in {"high", "critical"}),
                ]
                if enabled
            ) or "high_risk"
        }
        for row in high_risk_tickets[:12]
    ]
    return _apply_ai("risk", payload)


def _quality_summary(window: dict[str, Any], *, connection_factory: Any = db_connection) -> dict[str, Any]:
    with connection_factory() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket_summary = _fetch_one(
                cur,
                """
                SELECT COUNT(*) AS ticket_count
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                """,
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                (window["window_start"],),
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
                    latest_safety.safety_action,
                    latest_safety.retry_count
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
                (window["window_start"],),
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
                (window["window_start"],),
            )
            pipeline_counts = _fetch_one(
                cur,
                """
                SELECT
                    COUNT(*) AS ticket_count,
                    COUNT(*) FILTER (
                        WHERE NOT EXISTS (
                            SELECT 1 FROM ticket_analysis a WHERE a.ticket_id = t.ticket_id
                        )
                    ) AS tickets_without_analysis,
                    COUNT(*) FILTER (
                        WHERE NOT EXISTS (
                            SELECT 1 FROM answer_draft d WHERE d.ticket_id = t.ticket_id
                        )
                    ) AS tickets_without_draft,
                    COUNT(*) FILTER (
                        WHERE NOT EXISTS (
                            SELECT 1 FROM final_response fr WHERE fr.ticket_id = t.ticket_id
                        )
                    ) AS tickets_without_response
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                """,
                (window["window_start"],),
            ) or {}

    payload = build_quality_payload(
        window=window,
        ticket_summary=ticket_summary,
        draft_summary=draft_summary,
        evidence_summary=evidence_summary,
        safety_summary=safety_summary,
        final_response_summary=final_response_summary,
        notification_summary=notification_summary,
        quality_candidates=quality_candidates,
        notification_failures=notification_failures,
    )
    ticket_count = int(ticket_summary.get("ticket_count") or 0)
    draft_count = int(draft_summary.get("draft_count") or 0)
    payload["pipeline_gaps"] = {
        "tickets_without_analysis": int(pipeline_counts.get("tickets_without_analysis") or 0),
        "tickets_without_draft": int(pipeline_counts.get("tickets_without_draft") or 0),
        "tickets_without_response": int(pipeline_counts.get("tickets_without_response") or 0),
        "drafts_without_evidence": max(draft_count - int(draft_summary.get("evidence_linked_drafts") or 0), 0),
        "quality_watch_rate": rate(len(quality_candidates), ticket_count),
    }
    payload["failure_distribution"] = {
        "notification_channel_distribution": _distribution_rows(notification_failures, key="channel"),
        "notification_error_distribution": _distribution_rows(notification_failures, key="error_category"),
    }
    payload["coaching_queue"] = [
        {
            **row,
            "coaching_reason": ", ".join(
                reason
                for reason, enabled in [
                    ("low_factuality", (row.get("factuality_score") or 1) <= 0.3),
                    ("hallucination_risk", (row.get("hallucination_score") or 0) >= 0.7),
                    ("retry_detected", int(row.get("retry_count") or 0) > 0),
                ]
                if enabled
            ) or "quality_review"
        }
        for row in quality_candidates[:12]
    ]
    return _apply_ai("quality", payload)


class DashboardWorkflowService:
    """Section-oriented dashboard service without graph/node orchestration."""

    def __init__(self, *, connection_factory: Any = db_connection) -> None:
        self._connection_factory = connection_factory

    def overview(self, days: int) -> dict[str, Any]:
        return _overview_summary(_window(days), connection_factory=self._connection_factory)

    def risk(self, days: int) -> dict[str, Any]:
        return _risk_summary(_window(days), connection_factory=self._connection_factory)

    def quality(self, days: int) -> dict[str, Any]:
        return _quality_summary(_window(days), connection_factory=self._connection_factory)

    def all(self, days: int) -> dict[str, Any]:
        days = clamp_days(days)
        return {
            "window_days": days,
            "overview": self.overview(days),
            "risk": self.risk(days),
            "quality": self.quality(days),
        }


_SERVICE = DashboardWorkflowService()


def run_dashboard_workflow(section: DashboardSection, days: int) -> dict[str, Any]:
    """Return dashboard summary payloads through the service implementation."""

    normalized_section: DashboardSection = section
    if normalized_section == "overview":
        return _SERVICE.overview(days)
    if normalized_section == "risk":
        return _SERVICE.risk(days)
    if normalized_section == "quality":
        return _SERVICE.quality(days)
    return _SERVICE.all(days)
