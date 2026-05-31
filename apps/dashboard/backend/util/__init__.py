"""Shared calculation helpers for the dashboard."""

from .ai import generate_dashboard_interpretation, generate_review_row_interpretations
from .metrics import (
    build_overview_payload,
    build_quality_payload,
    build_risk_payload,
    build_window,
    clamp_days,
    format_minutes,
    mask_email,
    mask_identifier,
    rate,
    safe_average,
)

__all__ = [
    "generate_dashboard_interpretation",
    "generate_review_row_interpretations",
    "build_overview_payload",
    "build_quality_payload",
    "build_risk_payload",
    "build_window",
    "clamp_days",
    "format_minutes",
    "mask_email",
    "mask_identifier",
    "rate",
    "safe_average",
]
