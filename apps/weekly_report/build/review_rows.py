"""우선 확인 문의 행 선별 및 페이로드 포맷."""

from __future__ import annotations

from typing import Any

from build.distributions import normalize_text


def pick_review_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    """우선 확인이 필요한 행을 최대 limit개 반환한다.

    플래그 조건 (OR):
    - risk_level이 high/critical
    - routing_target이 urgent_alert/human_review (즉시 대응 필요)
    - sentiment가 negative/very_negative (이용자 불만)
    - summary가 비어 있는 행 (분석 미완료)

    조건에 맞는 행이 없으면 전체 rows의 앞 limit개를 반환해
    보고서의 '우선 확인' 섹션이 비어있지 않도록 한다.
    """
    flagged = [
        row for row in rows
        if normalize_text(row.get("risk_level")).lower() in {"high", "critical"}
        or normalize_text(row.get("routing_target")).lower() in {"urgent_alert", "human_review"}
        or normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
        or not normalize_text(row.get("summary"), fallback="").strip()
    ]
    return flagged[:limit] if flagged else rows[:limit]


def build_analysis_rows_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """전체 분석 행에서 PDF 분석 원본 테이블에 필요한 컬럼만 추출해 반환한다.

    analyzed_at은 datetime 객체이므로 JSON 직렬화가 가능한 ISO 문자열로 변환한다.
    """
    return [
        {
            "analysis_id": row.get("analysis_id"),
            "ticket_id": row.get("ticket_id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "source_type": row.get("source_type"),
            "category": row.get("category"),
            "responder_type": row.get("responder_type"),
            "enriched_query": row.get("enriched_query"),
            "risk_level": row.get("risk_level"),
            "sentiment": row.get("sentiment"),
            "routing_target": row.get("routing_target"),
            "summary": row.get("summary"),
            # analyzed_at이 None이면 isoformat() 호출이 AttributeError를 유발하므로 조건부로 처리한다.
            "analyzed_at": row.get("analyzed_at").isoformat() if row.get("analyzed_at") else None,
        }
        for row in rows
    ]
