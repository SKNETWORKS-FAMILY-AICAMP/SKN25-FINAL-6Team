"""조회 기간(window) 계산 — 모든 섹션에 넘겨주는 기준값."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from utils.stats import build_window, clamp_days


def get_window(days: int = 7, *, now: datetime | None = None) -> dict[str, Any]:
    """이번 주 window dict를 반환한다.

    clamp_days로 1~365일 범위를 강제한 뒤 build_window에 위임한다.
    now를 고정하면 이번 주·직전 주 window가 동일한 기준 시각을 공유해 기간 불일치를 방지한다.
    """
    return build_window(clamp_days(days), now=now)


def get_previous_window(window: dict[str, Any]) -> dict[str, Any]:
    """window를 기준으로 직전 동일 기간 window를 반환한다.

    이번 주 window_start를 직전 주의 window_end로 사용하므로
    두 기간이 겹치거나 빠지는 구간이 생기지 않는다.
    """
    days = int(window["days"])
    start: datetime = window["window_start"]
    return {
        "days": days,
        "window_start": start - timedelta(days=days),
        # 직전 주의 끝 = 이번 주의 시작 (반개구간 [prev_start, start))
        "window_end": start,
    }
