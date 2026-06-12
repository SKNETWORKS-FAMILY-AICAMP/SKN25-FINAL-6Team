"""유저 개선 요청 Top 5 집계.

두 가지 기준으로 상위 5개 카테고리를 반환한다.
  - by_count   : 문의 건수 기준 (가장 많이 들어온 카테고리)
  - by_severity: 심각도 가중치 합산 기준
      critical=3 / high=2 / medium=1 / low=0 (Grubbs 1969 척도 참고)

대상 테이블: ticket_analysis.category + risk_level
기간 필터  : qa_ticket.inquiry_created_at >= window_start AND < window_end
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from db import _fetch_all, db_connection, dict_row

_SEVERITY_WEIGHT: dict[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
    "unknown": 0,
}

TOP_N = 5


def fetch(window: dict[str, Any]) -> dict[str, Any]:
    """window 기간의 카테고리별 Top 5 집계를 반환한다.

    Returns:
        {
            "by_count": [{"category": str, "count": int}],
            "by_severity": [{"category": str, "weight": int}],
        }
    """
    start: datetime = window["window_start"]
    end: datetime = window["window_end"]

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(
                cur,
                """
                SELECT
                    COALESCE(a.category, 'unknown') AS category,
                    LOWER(COALESCE(a.risk_level, 'unknown')) AS risk_level,
                    COUNT(*) AS cnt
                FROM ticket_analysis a
                JOIN qa_ticket t ON t.ticket_id = a.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1, 2
                ORDER BY category, cnt DESC
                """,
                (start, end),
            )

    # 카테고리별 집계
    count_by_category: dict[str, int] = {}
    weight_by_category: dict[str, int] = {}

    for row in rows:
        cat = str(row["category"])
        cnt = int(row["cnt"])
        risk = str(row["risk_level"])
        weight = _SEVERITY_WEIGHT.get(risk, 0)

        count_by_category[cat] = count_by_category.get(cat, 0) + cnt
        weight_by_category[cat] = weight_by_category.get(cat, 0) + cnt * weight

    by_count = sorted(count_by_category.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]
    by_severity = sorted(weight_by_category.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]

    return {
        "by_count": [{"category": cat, "count": cnt} for cat, cnt in by_count],
        "by_severity": [{"category": cat, "weight": w} for cat, w in by_severity],
    }
