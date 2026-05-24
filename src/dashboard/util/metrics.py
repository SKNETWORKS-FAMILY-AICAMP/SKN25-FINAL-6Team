"""Pure calculation helpers used by the dashboard workflow and UI."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any


MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 30


def clamp_days(days: int | float | str, *, min_days: int = MIN_DAYS, max_days: int = MAX_DAYS) -> int:
    """Clamp the dashboard lookback window."""

    value = int(days)
    return max(min_days, min(value, max_days))


def build_window(days: int, *, now: datetime | None = None) -> dict[str, Any]:
    """Return the time window used by all dashboard queries."""

    current = now or datetime.now()
    days = clamp_days(days)
    return {
        "days": days,
        "window_start": current - timedelta(days=days),
        "window_end": current,
    }


def rate(numerator: int | float | None, denominator: int | float | None) -> float:
    """Return a safe ratio for dashboard KPI calculations."""

    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


def safe_average(values: list[int | float | None]) -> float | None:
    """Return the mean of non-null values, or None when no values exist."""

    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return float(mean(filtered))


def format_minutes(value: float | int | None) -> str:
    """Format a latency value in minutes for display."""

    if value is None:
        return "-"
    return f"{float(value):.1f}분"


def mask_identifier(value: object, *, keep_start: int = 3, keep_end: int = 2) -> str:
    """Mask a token-like identifier for list and detail views."""

    text = str(value or "").strip()
    if not text:
        return "-"
    if len(text) <= keep_start + keep_end:
        return "*" * len(text)
    return f"{text[:keep_start]}***{text[-keep_end:]}"


def mask_email(value: object) -> str:
    """Mask an email address while preserving its domain."""

    text = str(value or "").strip()
    if not text or "@" not in text:
        return mask_identifier(text)
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = f"{local[:2]}***"
    return f"{masked_local}@{domain}"


def _window_payload(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "days": int(window["days"]),
        "window_start": window["window_start"].isoformat(),
        "window_end": window["window_end"].isoformat(),
    }


def build_overview_payload(
    *,
    window: dict[str, Any],
    raw_counts: dict[str, Any],
    response_metrics: dict[str, Any],
    source_distribution: list[dict[str, Any]],
    status_distribution: list[dict[str, Any]],
    routing_distribution: list[dict[str, Any]],
    recent_tickets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the overview payload returned by the dashboard API."""

    total_tickets = int(raw_counts.get("total_tickets") or 0)
    pending_tickets = int(raw_counts.get("pending_tickets") or 0)
    closed_tickets = int(raw_counts.get("closed_tickets") or 0)
    today_tickets = int(raw_counts.get("today_tickets") or 0)
    old_pending_count = int(raw_counts.get("old_pending_count") or 0)
    responded_tickets = int(response_metrics.get("responded_tickets") or 0)
    draft_tickets = int(response_metrics.get("draft_tickets") or 0)
    analyzed_tickets = int(response_metrics.get("analyzed_tickets") or 0)

    return {
        "window": _window_payload(window),
        "ticket_counts": {
            "total": total_tickets,
            "pending": pending_tickets,
            "closed": closed_tickets,
            "today": today_tickets,
        },
        "response_metrics": {
            "response_rate": rate(responded_tickets, total_tickets),
            "draft_coverage_rate": rate(draft_tickets, total_tickets),
            "analysis_coverage_rate": rate(analyzed_tickets, total_tickets),
            "avg_response_latency_minutes": response_metrics.get("avg_response_latency_minutes"),
        },
        "coverage_metrics": {
            "response_rate": rate(responded_tickets, total_tickets),
            "draft_coverage_rate": rate(draft_tickets, total_tickets),
            "analysis_coverage_rate": rate(analyzed_tickets, total_tickets),
        },
        "source_distribution": source_distribution,
        "status_distribution": status_distribution,
        "routing_distribution": routing_distribution,
        "old_pending_count": old_pending_count,
        "recent_tickets": recent_tickets,
    }


def build_risk_payload(
    *,
    window: dict[str, Any],
    analysis_risk_distribution: list[dict[str, Any]],
    sentiment_distribution: list[dict[str, Any]],
    insight_risk_distribution: list[dict[str, Any]],
    pattern_risk_distribution: list[dict[str, Any]],
    safety_score_summary: dict[str, Any],
    high_risk_tickets: list[dict[str, Any]],
    safety_breach_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the risk payload returned by the dashboard API."""

    avg_hallucination = safety_score_summary.get("avg_hallucination_score")
    avg_toxicity = safety_score_summary.get("avg_toxicity_score")
    avg_policy = safety_score_summary.get("avg_policy_violation_score")
    avg_factuality = safety_score_summary.get("avg_factuality_score")

    return {
        "window": _window_payload(window),
        "analysis_risk_distribution": analysis_risk_distribution,
        "sentiment_distribution": sentiment_distribution,
        "insight_risk_distribution": insight_risk_distribution,
        "pattern_risk_distribution": pattern_risk_distribution,
        "safety_score_summary": {
            "avg_hallucination_score": avg_hallucination,
            "avg_toxicity_score": avg_toxicity,
            "avg_policy_violation_score": avg_policy,
            "avg_factuality_score": avg_factuality,
            "safety_check_count": int(safety_score_summary.get("safety_check_count") or 0),
        },
        "safety_alerts": {
            "high_hallucination": (avg_hallucination or 0) >= 0.7,
            "high_toxicity": (avg_toxicity or 0) >= 0.7,
            "high_policy_violation": (avg_policy or 0) >= 0.7,
            "low_factuality": avg_factuality is not None and avg_factuality <= 0.3,
        },
        "high_risk_tickets": high_risk_tickets,
        "safety_breach_candidates": safety_breach_candidates,
    }


def build_quality_payload(
    *,
    window: dict[str, Any],
    ticket_summary: dict[str, Any],
    draft_summary: dict[str, Any],
    evidence_summary: dict[str, Any],
    safety_summary: dict[str, Any],
    final_response_summary: dict[str, Any],
    notification_summary: list[dict[str, Any]],
    quality_candidates: list[dict[str, Any]],
    notification_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the quality payload returned by the dashboard API."""

    ticket_count = int(ticket_summary.get("ticket_count") or 0)
    draft_count = int(draft_summary.get("draft_count") or 0)
    evidence_linked_drafts = int(draft_summary.get("evidence_linked_drafts") or 0)
    final_response_count = int(final_response_summary.get("final_response_count") or 0)
    final_response_ticket_count = int(final_response_summary.get("final_response_ticket_count") or 0)
    evidence_count = int(evidence_summary.get("evidence_count") or 0)

    return {
        "window": _window_payload(window),
        "draft_summary": {
            "draft_count": draft_count,
            "draft_ticket_count": int(draft_summary.get("draft_ticket_count") or 0),
            "evidence_linked_drafts": evidence_linked_drafts,
            "avg_draft_latency_minutes": draft_summary.get("avg_draft_latency_minutes"),
        },
        "evidence_summary": {
            "evidence_count": evidence_count,
            "avg_relevance_score": evidence_summary.get("avg_relevance_score"),
            "avg_retrieval_rank": evidence_summary.get("avg_retrieval_rank"),
        },
        "safety_summary": {
            "avg_hallucination_score": safety_summary.get("avg_hallucination_score"),
            "avg_toxicity_score": safety_summary.get("avg_toxicity_score"),
            "avg_policy_violation_score": safety_summary.get("avg_policy_violation_score"),
            "avg_factuality_score": safety_summary.get("avg_factuality_score"),
            "safety_check_count": int(safety_summary.get("safety_check_count") or 0),
        },
        "final_response_summary": {
            "final_response_count": final_response_count,
            "final_response_ticket_count": final_response_ticket_count,
            "avg_final_latency_minutes": final_response_summary.get("avg_final_latency_minutes"),
        },
        "notification_summary": notification_summary,
        "coverage_metrics": {
            "draft_ticket_rate": rate(draft_summary.get("draft_ticket_count"), ticket_count),
            "evidence_attachment_rate": rate(evidence_linked_drafts, draft_count),
            "final_response_ticket_rate": rate(final_response_ticket_count, ticket_count),
        },
        "quality_candidates": quality_candidates,
        "notification_failures": notification_failures,
    }
