"""급증·위험 문의 현황 감지.

방법론 1: Z-Score — 시간별 폭증 감지
  Z = (이번 주 관측값 - 과거 4주 동일 시간대 평균) / 과거 4주 동일 시간대 표준편차
  Z ≥ 2.0 → warning / Z ≥ 3.0 → critical
  근거: Grubbs(1969) / Chandola et al.(2009) ACM Computing Surveys

방법론 2: WoW — 일별 폭증 감지
  WoW 증가율 = (이번 주 요일별 건수 - 전주 동일 요일 건수) / 전주 동일 요일 건수
  ≥ +50% → warning / ≥ +100% → critical
  근거: Taylor & Letham(2018) Prophet / Cleveland et al.(1990) STL

방법론 3: 월별 추세 — 직전 4주 총 건수 바차트
  임계값 없음. 추세 시각화 목적.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from db.connection import _fetch_all, db_connection, dict_row

# Z-Score 임계값: Grubbs(1969) 기준 — 2.0은 95%, 3.0은 99.7% 신뢰 수준.
_ZSCORE_WARNING = 2.0
_ZSCORE_CRITICAL = 3.0
# WoW 임계값: +50% = warning, +100% = critical (2배 이상이면 즉시 주의).
_WOW_WARNING = 0.5
_WOW_CRITICAL = 1.0
# 기준선을 구성할 과거 주 수 — 4주가 계절성 없는 게임 CS 패턴에 충분하다.
_PAST_WEEKS = 4


def _zscore_level(zscore: float) -> str:
    """Z-Score를 warning/critical/normal 레벨로 분류한다."""
    if zscore >= _ZSCORE_CRITICAL:
        return "critical"
    if zscore >= _ZSCORE_WARNING:
        return "warning"
    return "normal"


def _wow_level(pct_change: float) -> str:
    """WoW 증가율을 warning/critical/normal 레벨로 분류한다."""
    if pct_change >= _WOW_CRITICAL:
        return "critical"
    if pct_change >= _WOW_WARNING:
        return "warning"
    return "normal"


def _calculate_zscore_by_hour(window: dict[str, Any]) -> list[dict[str, Any]]:
    """시간대별 Z-Score 계산 (방법론 1).

    현재 주 각 시간대의 문의 건수를 과거 4주 동일 시간대 건수와 비교한다.
    과거 데이터가 2주 미만인 시간대는 표준편차를 신뢰할 수 없어 건너뛴다.
    결과에는 normal 레벨 항목을 포함하지 않는다.
    """
    current_start: datetime = window["window_start"]
    current_end: datetime = window["window_end"]
    past_start = current_start - timedelta(weeks=_PAST_WEEKS)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # 현재 주: 시간대별 총 건수
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
            # 과거 4주: 시간대 × 주별 건수 (주별로 나눠야 표준편차 계산 가능)
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

    # hour → [주별 건수 리스트] 로 정리해 평균·표준편차를 계산한다.
    past_by_hour: dict[int, list[float]] = {}
    for row in past_rows:
        h = int(row["hour"])
        past_by_hour.setdefault(h, []).append(float(row["cnt"]))

    current_by_hour = {int(r["hour"]): int(r["cnt"]) for r in current_rows}

    results = []
    for hour in range(24):
        current_cnt = current_by_hour.get(hour, 0)
        past_counts = past_by_hour.get(hour, [])

        # 과거 데이터가 2주 미만이면 표준편차가 0에 수렴하거나 편향이 심해 Z-Score를 신뢰할 수 없다.
        if len(past_counts) < 2:
            continue

        avg = sum(past_counts) / len(past_counts)
        variance = sum((x - avg) ** 2 for x in past_counts) / len(past_counts)
        std = math.sqrt(variance)

        # 표준편차가 0이면 모든 과거 값이 동일 → Z-Score를 0으로 처리해 오탐을 방지한다.
        zscore = 0.0 if std == 0 else (current_cnt - avg) / std

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

    # Z-Score 내림차순 정렬 — 가장 이상한 시간대가 상단에 오도록 한다.
    return sorted(results, key=lambda x: -x["zscore"])


def _calculate_wow_by_day(window: dict[str, Any]) -> list[dict[str, Any]]:
    """일별 WoW 증가율 계산 (방법론 2).

    같은 요일끼리 비교하기 위해 ISODOW(ISO 요일: 1=월 ~ 7=일)를 기준으로 매핑한다.
    전주 데이터가 없는 요일은 이번 주 건수를 증가율로 사용한다 (신규 요일 취급).
    결과에는 normal 레벨 항목을 포함하지 않는다.
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

    # dow → (요일명, 건수) 로 정리해 요일별 WoW 비교에 활용한다.
    current_by_dow = {int(r["dow"]): (r["day_name"].strip(), int(r["cnt"])) for r in current_rows}
    prev_by_dow = {int(r["dow"]): int(r["cnt"]) for r in prev_rows}

    # DOW 1(월)~7(일) 전체를 순서대로 반환 — 데이터 없는 요일도 0건으로 포함해 7일 바차트에 사용.
    results = []
    for dow in range(1, 8):
        if dow in current_by_dow:
            day_name, this_cnt = current_by_dow[dow]
        else:
            day_name = _DOW_NAMES_KO[dow]
            this_cnt = 0

        prev_cnt = prev_by_dow.get(dow, 0)
        if prev_cnt == 0:
            pct_change = float(this_cnt) if this_cnt > 0 else 0.0
        else:
            pct_change = (this_cnt - prev_cnt) / prev_cnt

        results.append({
            "dow": dow,
            "day": day_name,
            "this_week": this_cnt,
            "prev_week": prev_cnt,
            "pct_change": round(pct_change, 4),
            "level": _wow_level(pct_change),
        })

    return results


_DOW_NAMES_KO: dict[int, str] = {
    1: "월요일", 2: "화요일", 3: "수요일",
    4: "목요일", 5: "금요일", 6: "토요일", 7: "일요일",
}

# week_offset → 한국어 레이블 (0=이번 주, -1=1주 전, ...)
_WEEK_LABELS = {0: "이번 주", -1: "1주 전", -2: "2주 전", -3: "3주 전"}


def _calculate_monthly_trend(window: dict[str, Any]) -> list[dict[str, Any]]:
    """직전 4주 총 건수 집계 (방법론 3) — 추세 시각화 목적.

    임계값이 없고 차트용 bar 데이터로만 사용된다.
    4개 기간을 하나의 CASE 쿼리로 집계해 DB 왕복을 1회로 줄인다.
    """
    current_start: datetime = window["window_start"]
    current_end: datetime = window["window_end"]
    days = int(window.get("days", 7))

    # 각 주의 시작·끝을 미리 계산한다 (w_starts[0]=이번 주, w_starts[3]=3주 전).
    w_starts = [current_start - timedelta(days=days * i) for i in range(4)]
    w_ends = [current_start - timedelta(days=days * i) + timedelta(days=days) for i in range(4)]
    # 이번 주 끝은 current_end (기준 시각)로 고정해 미래 데이터가 섞이지 않게 한다.
    w_ends[0] = current_end
    four_weeks_start = w_starts[3]

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(
                cur,
                """
                SELECT
                    CASE
                        WHEN inquiry_created_at >= %s AND inquiry_created_at < %s THEN 0
                        WHEN inquiry_created_at >= %s AND inquiry_created_at < %s THEN -1
                        WHEN inquiry_created_at >= %s AND inquiry_created_at < %s THEN -2
                        WHEN inquiry_created_at >= %s AND inquiry_created_at < %s THEN -3
                    END AS week_offset,
                    COUNT(*) AS cnt
                FROM qa_ticket
                WHERE inquiry_created_at >= %s
                  AND inquiry_created_at < %s
                GROUP BY 1
                ORDER BY 1 DESC
                """,
                (
                    w_starts[0], w_ends[0],
                    w_starts[1], w_ends[1],
                    w_starts[2], w_ends[2],
                    w_starts[3], w_ends[3],
                    four_weeks_start, current_end,
                ),
            )

    # week_offset이 None인 행은 CASE에서 매칭되지 않은 행이므로 제외한다.
    count_by_offset = {int(r["week_offset"]): int(r["cnt"]) for r in rows if r["week_offset"] is not None}

    # 데이터가 없는 주는 0건으로 채워 차트가 빈 막대로 표시되게 한다.
    return [
        {
            "week_offset": offset,
            "label": _WEEK_LABELS[offset],
            "count": count_by_offset.get(offset, 0),
        }
        for offset in (0, -1, -2, -3)
    ]


def build_spike_slack_blocks(alerts: dict[str, Any]) -> list[dict]:
    """폭증 감지 결과를 Slack Block Kit 형식으로 변환한다.

    hourly에는 Z-Score 크기를 블록(█) 막대로 시각화해 한눈에 파악할 수 있게 한다.
    이상 없을 경우 단일 안내 블록을 반환한다.
    """
    hourly: list[dict] = alerts.get("hourly", [])
    daily: list[dict] = alerts.get("daily", [])

    if not hourly and not daily:
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "✅ 이번 주 이상 폭증 감지 없음"},
            }
        ]

    blocks: list[dict] = []

    if hourly:
        lines = ["*[시간별 문의 집중도]*"]
        for item in hourly:
            # Z-Score를 최대 5칸 막대로 클리핑해 Slack 메시지가 지나치게 길어지지 않게 한다.
            bar_len = min(int(item["zscore"]), 5)
            bar = "█" * bar_len
            lines.append(f"{item['hour']:02d}시  {bar}  {item['level']} (Z={item['zscore']})")
        lines.append("_※ 정상 시간대 생략_")
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}
        )

    anomaly_daily = [d for d in daily if d.get("level") != "normal"]
    if anomaly_daily:
        lines = ["*[일별 폭증 감지]*"]
        for item in anomaly_daily:
            pct = item["pct_change"] * 100
            lines.append(f"{item['day']}  {pct:+.1f}%  ({item['level']})")
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}
        )

    return blocks


def detect(window: dict[str, Any]) -> dict[str, Any]:
    """세 가지 방법론으로 폭증·위험 현황을 감지해 반환한다.

    반환 구조:
    {
        "hourly":  [Z-Score 이상 시간대 리스트],
        "daily":   [WoW 이상 요일 리스트],
        "monthly": [직전 4주 추세 리스트],
    }
    """
    return {
        "hourly": _calculate_zscore_by_hour(window),
        "daily": _calculate_wow_by_day(window),
        "monthly": _calculate_monthly_trend(window),
    }
