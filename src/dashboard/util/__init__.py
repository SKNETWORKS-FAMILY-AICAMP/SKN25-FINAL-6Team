"""Shared calculation helpers for the dashboard."""

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
