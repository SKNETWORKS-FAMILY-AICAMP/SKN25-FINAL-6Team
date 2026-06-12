"""조회 기간(window) 계산 — 모든 섹션에 넘겨주는 기준값."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from utils.stats import build_window, clamp_days


def get_window(days: int = 7, *, now: datetime | None = None) -> dict[str, Any]:
    """이번 주 window dict를 반환한다."""
    return build_window(clamp_days(days), now=now)


def get_previous_window(window: dict[str, Any]) -> dict[str, Any]:
    """window를 기준으로 직전 동일 기간 window를 반환한다."""
    days = int(window["days"])
    start: datetime = window["window_start"]
    return {
        "days": days,
        "window_start": start - timedelta(days=days),
        "window_end": start,
    }
