"""유저 개선 요청 Top 5 집계 — Nielsen(1994) 빈도×심각도 가중합 방식.

공식: priority_score = (발생 건수 × 0.4) + (심각도 등급 × 0.6)
심각도 등급: critical=4 / high=3 / medium=2 / low=1  (Nielsen 0~4 척도)
개선 유형 : critical/high → 설계 결함 / medium/low → 편의 개선

대상 테이블: ticket_analysis, qa_ticket, voc_feedback
기간 필터  : qa_ticket.inquiry_created_at >= window_start AND < window_end
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from db.connection import _fetch_all, db_connection, dict_row

_NIELSEN_GRADE: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 1,
}

_SCORE_TO_LEVEL: dict[int, str] = {4: "critical", 3: "high", 2: "medium", 1: "low"}

TOP_N = 5


def get_risk_level_score(risk_level: str) -> int:
    return _NIELSEN_GRADE.get(risk_level.lower(), 1)


def classify_improvement_type(row: dict) -> str:
    if row.get("level") in ("critical", "high"):
        return "설계 결함"
    return "편의 개선"


def _fetch_category_keywords(
    cur, start: datetime, end: datetime, categories: list[str]
) -> dict[str, list[str]]:
    """카테고리별 상위 키워드 최대 3개를 반환한다."""
    if not categories:
        return {}
    rows = _fetch_all(
        cur,
        """
        SELECT
            COALESCE(a.category, 'unknown') AS category,
            v.topic_keywords
        FROM ticket_analysis a
        JOIN qa_ticket t ON t.ticket_id = a.ticket_id
        LEFT JOIN voc_feedback v ON v.ticket_id = a.ticket_id
        WHERE t.inquiry_created_at >= %s
          AND t.inquiry_created_at < %s
          AND v.topic_keywords IS NOT NULL
          AND COALESCE(a.category, 'unknown') = ANY(%s)
        """,
        (start, end, categories),
    )

    freq_by_cat: dict[str, dict[str, int]] = {}
    for row in rows:
        cat = str(row["category"])
        kw_raw = row.get("topic_keywords")
        if not kw_raw:
            continue
        keywords: list[str] = (
            [str(k).strip() for k in kw_raw if k]
            if isinstance(kw_raw, list)
            else [k.strip() for k in str(kw_raw).split(",") if k.strip()]
        )
        freq = freq_by_cat.setdefault(cat, {})
        for kw in keywords:
            freq[kw] = freq.get(kw, 0) + 1

    return {
        cat: [kw for kw, _ in sorted(freq.items(), key=lambda x: -x[1])[:3]]
        for cat, freq in freq_by_cat.items()
    }


def calculate_priority_score(window: dict[str, Any]) -> list[dict[str, Any]]:
    """카테고리별 가중합 점수를 계산하고 내림차순으로 반환한다."""
    start: datetime = window["window_start"]
    end: datetime = window["window_end"]

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(
                cur,
                """
                SELECT
                    COALESCE(a.category, 'unknown') AS category,
                    COUNT(*) AS cnt,
                    MAX(CASE LOWER(COALESCE(a.risk_level, 'unknown'))
                        WHEN 'critical' THEN 4
                        WHEN 'high'     THEN 3
                        WHEN 'medium'   THEN 2
                        WHEN 'low'      THEN 1
                        ELSE 1
                    END) AS severity_score
                FROM ticket_analysis a
                JOIN qa_ticket t ON t.ticket_id = a.ticket_id
                WHERE t.inquiry_created_at >= %s
                  AND t.inquiry_created_at < %s
                GROUP BY 1
                """,
                (start, end),
            )
            categories = [str(r["category"]) for r in rows]
            keywords_map = _fetch_category_keywords(cur, start, end, categories)

    result: list[dict[str, Any]] = []
    for row in rows:
        cat = str(row["category"])
        cnt = int(row["cnt"])
        severity_score = int(row["severity_score"])
        level = _SCORE_TO_LEVEL.get(severity_score, "low")
        priority_score = round((cnt * 0.4) + (severity_score * 0.6), 1)
        result.append(
            {
                "category": cat,
                "count": cnt,
                "severity_score": severity_score,
                "priority_score": priority_score,
                "level": level,
                "topic_keywords": keywords_map.get(cat, []),
            }
        )

    return sorted(result, key=lambda x: (-x["priority_score"], x["category"]))


def build_top5_slack_blocks(top5: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for item in top5:
        kw_text = " / ".join(item["topic_keywords"]) if item.get("topic_keywords") else "—"
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*#{item['rank']} {item['category']}*\n{kw_text}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*{item['count']}건* | {item['level']} | 점수 {item['priority_score']:.1f}\n"
                            f"`{item['improvement_type']}`"
                        ),
                    },
                ],
            }
        )
        blocks.append({"type": "divider"})
    return blocks


def fetch(window: dict[str, Any]) -> list[dict[str, Any]]:
    scored = calculate_priority_score(window)
    return [
        {
            "rank": i + 1,
            **item,
            "improvement_type": classify_improvement_type(item),
        }
        for i, item in enumerate(scored[:TOP_N])
    ]
