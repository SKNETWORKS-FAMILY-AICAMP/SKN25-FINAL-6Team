"""통계·계산 유틸 — 비율, 평균, 기간 계산."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any

# 조회 기간 상·하한: 1일 미만 또는 1년 초과는 운영상 의미 없으므로 클램핑한다.
MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 30


def clamp_days(days: int | float | str, *, min_days: int = MIN_DAYS, max_days: int = MAX_DAYS) -> int:
    """days를 [min_days, max_days] 범위로 클램핑해 int로 반환한다.

    문자열로 넘어와도 int()로 먼저 변환하므로 Airflow 환경변수 값도 그대로 사용할 수 있다.
    """
    value = int(days)
    return max(min_days, min(value, max_days))


def build_window(days: int, *, now: datetime | None = None) -> dict[str, Any]:
    """기준 시각 now에서 days일 전까지의 window dict를 반환한다.

    반환 구조: {"days": int, "window_start": datetime, "window_end": datetime}
    now를 고정하면 같은 기준 시각을 공유하는 여러 window를 일관되게 만들 수 있다.
    """
    current = now or datetime.now()
    days = clamp_days(days)
    return {
        "days": days,
        "window_start": current - timedelta(days=days),
        "window_end": current,
    }


def rate(numerator: int | float | None, denominator: int | float | None) -> float:
    """분자/분모 비율을 계산한다. 분모가 0이거나 None이면 0.0을 반환한다.

    ZeroDivisionError를 방지하기 위해 `not denominator`로 0과 None을 함께 처리한다.
    """
    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


def safe_average(values: list[int | float | None]) -> float | None:
    """None을 제외한 값들의 평균을 반환한다. 유효한 값이 없으면 None을 반환한다.

    None을 0으로 처리하면 분석 시각이 없는 행이 평균을 낮추는 오류가 생기므로
    아예 제외하고, 리스트 전체가 None이면 None을 반환한다.
    """
    filtered = [float(v) for v in values if v is not None]
    if not filtered:
        return None
    return float(mean(filtered))
