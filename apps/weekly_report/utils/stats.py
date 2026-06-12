"""통계·계산 유틸 — 비율, 평균, 기간 계산."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any

MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 30


def clamp_days(days: int | float | str, *, min_days: int = MIN_DAYS, max_days: int = MAX_DAYS) -> int:
    value = int(days)
    return max(min_days, min(value, max_days))


def build_window(days: int, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    days = clamp_days(days)
    return {
        "days": days,
        "window_start": current - timedelta(days=days),
        "window_end": current,
    }


def rate(numerator: int | float | None, denominator: int | float | None) -> float:
    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


def safe_average(values: list[int | float | None]) -> float | None:
    filtered = [float(v) for v in values if v is not None]
    if not filtered:
        return None
    return float(mean(filtered))
