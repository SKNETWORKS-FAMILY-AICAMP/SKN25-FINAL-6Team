"""급증·위험 문의 현황 감지.

방법론 1: Z-Score — 시간별 폭증 감지
  Z = (이번 주 관측값 - 과거 4주 동일 시간대 평균) / 과거 4주 동일 시간대 표준편차
  Z ≥ 2.0 → warning / Z ≥ 3.0 → critical
  근거: Grubbs(1969) / Chandola et al.(2009) ACM Computing Surveys

방법론 2: WoW — 일별 폭증 감지
  WoW 증가율 = (이번 주 요일별 건수 - 전주 동일 요일 건수) / 전주 동일 요일 건수
  ≥ +50% → warning / ≥ +100% → critical
  근거: Taylor & Letham(2018) Prophet / Cleveland et al.(1990) STL

방법론 3: 카테고리별 WoW (방법론 2 확장)
  ticket_analysis.category 단위로 WoW 계산
  > 50% → warning / > 100% → critical
  IQR 미채택: 카테고리별 데이터 소규모 시 기준 불안정
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from db import _fetch_all, db_connection, dict_row

_ZSCORE_WARNING = 2.0
_ZSCORE_CRITICAL = 3.0
_WOW_WARNING = 0.5
_WOW_CRITICAL = 1.0
_PAST_WEEKS = 4  # Z-Score 기준 과거 주 수


def _zscore_level(zscore: float) -> str:
    if zscore >= _ZSCORE_CRITICAL:
        return "critical"
    if zscore >= _ZSCORE_WARNING:
        return "warning"
    return "normal"


def _wow_level(pct_change: float) -> str:
    if pct_change >= _WOW_CRITICAL:
        return "critical"
    if pct_change >= _WOW_WARNING:
        return "warning"
    return "normal"


def _calculate_zscore_by_hour(window: dict[str, Any]) -> list[dict[str, Any]]:
    """시간대별 Z-Score 계산 (방법론 1).

    이번 주 각 시간대 건수와 과거 4주 동일 시간대 평균/표준편차를 비교한다.
    """
    current_start: datetime = window["window_start"]
    current_end: datetime = window["window_end"]
    # 과거 4주 기간
    past_start = current_start - timedelta(weeks=_PAST_WEEKS)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # 이번 주 시간대별 건수
            current_rows = _fetch_all(
                cur,
                """
                SELECT
                    EXTRACT(HOUR FROM t.inquiry_created_at)::int AS hour,
                    COUNT(*) AS cnt
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1
                """,
                (current_start, current_end),
            )
            # 과거 4주 시간대별 주별 건수
            past_rows = _fetch_all(
                cur,
                """
                SELECT
                    EXTRACT(HOUR FROM t.inquiry_created_at)::int AS hour,
                    DATE_TRUNC('week', t.inquiry_created_at) AS week_start,
                    COUNT(*) AS cnt
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1, 2
                """,
                (past_start, current_start),
            )

    # 과거 시간대별 주별 건수 집계
    past_by_hour: dict[int, list[float]] = {}
    for row in past_rows:
        h = int(row["hour"])
        past_by_hour.setdefault(h, []).append(float(row["cnt"]))

    current_by_hour = {int(r["hour"]): int(r["cnt"]) for r in current_rows}

    results = []
    for hour in range(24):
        current_cnt = current_by_hour.get(hour, 0)
        past_counts = past_by_hour.get(hour, [])

        if len(past_counts) < 2:
            # 기준 데이터 부족 → 계산 생략
            continue

        avg = sum(past_counts) / len(past_counts)
        variance = sum((x - avg) ** 2 for x in past_counts) / len(past_counts)
        std = math.sqrt(variance)

        if std == 0:
            zscore = 0.0
        else:
            zscore = (current_cnt - avg) / std

        level = _zscore_level(zscore)
        if level != "normal":
            results.append({
                "hour": hour,
                "avg": round(avg, 2),
                "std": round(std, 2),
                "current": current_cnt,
                "zscore": round(zscore, 2),
                "level": level,
            })

    return sorted(results, key=lambda x: -x["zscore"])


def _calculate_wow_by_day(window: dict[str, Any]) -> list[dict[str, Any]]:
    """일별 WoW 증가율 계산 (방법론 2).

    이번 주 요일별 건수와 전주 동일 요일 건수를 비교한다.
    """
    current_start: datetime = window["window_start"]
    current_end: datetime = window["window_end"]
    days = int(window.get("days", 7))
    prev_start = current_start - timedelta(days=days)
    prev_end = current_start

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current_rows = _fetch_all(
                cur,
                """
                SELECT
                    TO_CHAR(t.inquiry_created_at, 'Day') AS day_name,
                    EXTRACT(ISODOW FROM t.inquiry_created_at)::int AS dow,
                    COUNT(*) AS cnt
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1, 2
                ORDER BY 2
                """,
                (current_start, current_end),
            )
            prev_rows = _fetch_all(
                cur,
                """
                SELECT
                    TO_CHAR(t.inquiry_created_at, 'Day') AS day_name,
                    EXTRACT(ISODOW FROM t.inquiry_created_at)::int AS dow,
                    COUNT(*) AS cnt
                FROM qa_ticket t
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1, 2
                ORDER BY 2
                """,
                (prev_start, prev_end),
            )

    current_by_dow = {int(r["dow"]): (r["day_name"].strip(), int(r["cnt"])) for r in current_rows}
    prev_by_dow = {int(r["dow"]): int(r["cnt"]) for r in prev_rows}

    results = []
    for dow, (day_name, this_cnt) in current_by_dow.items():
        prev_cnt = prev_by_dow.get(dow, 0)
        if prev_cnt == 0:
            pct_change = float(this_cnt) if this_cnt > 0 else 0.0
        else:
            pct_change = (this_cnt - prev_cnt) / prev_cnt

        level = _wow_level(pct_change)
        if level != "normal":
            results.append({
                "day": day_name,
                "this_week": this_cnt,
                "prev_week": prev_cnt,
                "pct_change": round(pct_change, 4),
                "level": level,
            })

    return sorted(results, key=lambda x: -x["pct_change"])


def _calculate_wow_by_category(window: dict[str, Any]) -> list[dict[str, Any]]:
    """카테고리별 WoW 증가율 계산 (방법론 3).

    ticket_analysis.category 단위로 이번 주 / 전주 건수를 비교한다.
    """
    current_start: datetime = window["window_start"]
    current_end: datetime = window["window_end"]
    days = int(window.get("days", 7))
    prev_start = current_start - timedelta(days=days)
    prev_end = current_start

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current_rows = _fetch_all(
                cur,
                """
                SELECT
                    COALESCE(a.category, 'unknown') AS category,
                    COUNT(DISTINCT t.ticket_id) AS cnt
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT category
                    FROM ticket_analysis a
                    WHERE a.ticket_id = t.ticket_id
                    ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                    LIMIT 1
                ) a ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1
                """,
                (current_start, current_end),
            )
            prev_rows = _fetch_all(
                cur,
                """
                SELECT
                    COALESCE(a.category, 'unknown') AS category,
                    COUNT(DISTINCT t.ticket_id) AS cnt
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT category
                    FROM ticket_analysis a
                    WHERE a.ticket_id = t.ticket_id
                    ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                    LIMIT 1
                ) a ON TRUE
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1
                """,
                (prev_start, prev_end),
            )

    current_by_cat = {r["category"]: int(r["cnt"]) for r in current_rows}
    prev_by_cat = {r["category"]: int(r["cnt"]) for r in prev_rows}

    results = []
    for category, this_cnt in current_by_cat.items():
        prev_cnt = prev_by_cat.get(category, 0)
        if prev_cnt == 0:
            pct_change = float(this_cnt) if this_cnt > 0 else 0.0
        else:
            pct_change = (this_cnt - prev_cnt) / prev_cnt

        level = _wow_level(pct_change)
        if level != "normal":
            results.append({
                "category": category,
                "this_week": this_cnt,
                "prev_week": prev_cnt,
                "pct_change": round(pct_change, 4),
                "level": level,
            })

    return sorted(results, key=lambda x: -x["pct_change"])


def detect(window: dict[str, Any]) -> dict[str, Any]:
    """세 가지 방법론으로 폭증·위험 현황을 감지해 반환한다.

    Returns:
        {
            "hourly":      [{"hour", "avg", "std", "current", "zscore", "level"}],  # Z-Score
            "daily":       [{"day", "this_week", "prev_week", "pct_change", "level"}],  # WoW
            "by_category": [{"category", "this_week", "prev_week", "pct_change", "level"}],  # WoW
        }
    """
    return {
        "hourly": _calculate_zscore_by_hour(window),
        "daily": _calculate_wow_by_day(window),
        "by_category": _calculate_wow_by_category(window),
    }
