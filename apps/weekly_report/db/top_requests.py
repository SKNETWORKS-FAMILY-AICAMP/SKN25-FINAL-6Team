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

from common.observability.langfuse import observe_if_enabled
from db.connection import _fetch_all, db_connection, dict_row
from weekly_report_langfuse import link_weekly_report_trace

# Nielsen(1994) 심각도 0~4 척도를 정수로 매핑한다.
# unknown은 최소 심각도(1)로 처리해 미분류 항목이 상위에 오르지 않게 한다.
_NIELSEN_GRADE: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 1,
}

# 심각도 정수 → 레벨 문자열 역매핑 (DB MAX 결과를 레이블로 변환할 때 사용).
_SCORE_TO_LEVEL: dict[int, str] = {4: "critical", 3: "high", 2: "medium", 1: "low"}

TOP_N = 5


def get_risk_level_score(risk_level: str) -> int:
    """risk_level 문자열을 Nielsen 심각도 정수(1~4)로 변환한다."""
    return _NIELSEN_GRADE.get(risk_level.lower(), 1)


def classify_improvement_type(row: dict) -> str:
    """심각도 레벨을 바탕으로 개선 유형을 반환한다.

    critical/high → '설계 결함': 즉시 수정이 필요한 구조적 문제.
    medium/low    → '편의 개선': 사용성 향상 수준의 개선 사항.
    """
    if row.get("level") in ("critical", "high"):
        return "설계 결함"
    return "편의 개선"


def _fetch_category_keywords(
    cur, start: datetime, end: datetime, categories: list[str]
) -> dict[str, list[str]]:
    """카테고리별 상위 키워드 최대 3개를 반환한다.

    voc_feedback.topic_keywords는 list(배열) 또는 쉼표 구분 문자열로 저장될 수 있어
    두 형식을 모두 파싱한 뒤 빈도순으로 정렬해 상위 3개를 선택한다.
    """
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
        # psycopg3는 배열 컬럼을 Python list로 반환하지만, 문자열로 저장된 경우도 처리한다.
        keywords: list[str] = (
            [str(k).strip() for k in kw_raw if k]
            if isinstance(kw_raw, list)
            else [k.strip() for k in str(kw_raw).split(",") if k.strip()]
        )
        freq = freq_by_cat.setdefault(cat, {})
        for kw in keywords:
            freq[kw] = freq.get(kw, 0) + 1

    # 각 카테고리에서 출현 빈도 내림차순 상위 3개 키워드만 반환한다.
    return {
        cat: [kw for kw, _ in sorted(freq.items(), key=lambda x: -x[1])[:3]]
        for cat, freq in freq_by_cat.items()
    }


def calculate_priority_score(window: dict[str, Any]) -> list[dict[str, Any]]:
    """카테고리별 가중합 우선순위 점수를 계산하고 내림차순으로 반환한다.

    공식: priority_score = (발생 건수 × 0.4) + (심각도 등급 × 0.6)
    심각도를 가중치 0.6으로 더 높게 설정한 이유는 건수가 많더라도 낮은 위험도 문의가
    치명적 문의보다 앞에 오지 않도록 하기 위함이다.
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
                    COUNT(*) AS cnt,
                    -- 카테고리 내 가장 심각한 위험도를 대표값으로 사용한다 (MAX).
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
            try:
                keywords_map = _fetch_category_keywords(cur, start, end, categories)
            except Exception:
                keywords_map = {}

    result: list[dict[str, Any]] = []
    for row in rows:
        cat = str(row["category"])
        cnt = int(row["cnt"])
        severity_score = int(row["severity_score"])
        level = _SCORE_TO_LEVEL.get(severity_score, "low")
        # Nielsen 가중합 공식 적용
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

    # 점수 내림차순 정렬, 동점 시 카테고리명 오름차순으로 재현 가능한 순서를 보장한다.
    return sorted(result, key=lambda x: (-x["priority_score"], x["category"]))


def build_top5_slack_blocks(top5: list[dict]) -> list[dict]:
    """Top 5 결과를 Slack Block Kit section + divider 형식으로 변환한다.

    Slack의 fields 레이아웃을 사용해 카테고리/키워드와 건수/점수를 2열로 표시한다.
    """
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


@observe_if_enabled(
    name="weekly_report_fetch_top_requests",
    as_type="generation",
    tags=["weekly-report", "feature:data-fetch", "source:top-requests"],
)
def fetch(window: dict[str, Any]) -> list[dict[str, Any]]:
    """우선순위 점수 기준 상위 TOP_N개를 rank와 improvement_type을 붙여 반환한다."""
    link_weekly_report_trace(
        window,
        tags=["weekly-report", "feature:data-fetch", "source:top-requests"],
        input_payload={
            "window_start": window["window_start"].isoformat(),
            "window_end": window["window_end"].isoformat(),
            "days": window["days"],
        },
        window_start=window["window_start"].isoformat(),
        window_end=window["window_end"].isoformat(),
        days=int(window["days"]),
    )
    scored = calculate_priority_score(window)
    result = [
        {
            "rank": i + 1,
            **item,
            # rank를 붙인 후 improvement_type을 추가해 분류 기준이 level임을 명시한다.
            "improvement_type": classify_improvement_type(item),
        }
        for i, item in enumerate(scored[:TOP_N])
    ]
    link_weekly_report_trace(
        {"window_start": window["window_start"].isoformat(), "window_end": window["window_end"].isoformat()},
        tags=["weekly-report", "feature:data-fetch", "source:top-requests"],
        output_payload={"top_requests_count": len(result)},
        window_start=window["window_start"].isoformat(),
        window_end=window["window_end"].isoformat(),
        top_requests_count=len(result),
    )
    return result
