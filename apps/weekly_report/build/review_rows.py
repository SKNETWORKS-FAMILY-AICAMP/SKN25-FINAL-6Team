"""우선 확인 문의 행 선별 및 페이로드 포맷."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from build.distributions import normalize_text


def pick_review_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    flagged = [
        row for row in rows
        if normalize_text(row.get("risk_level")).lower() in {"high", "critical"}
        or normalize_text(row.get("routing_target")).lower() in {"urgent_alert", "human_review"}
        or normalize_text(row.get("sentiment")).lower() in {"negative", "very_negative"}
        or not normalize_text(row.get("summary"), fallback="").strip()
    ]
    return flagged[:limit] if flagged else rows[:limit]


def build_analysis_rows_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            "analyzed_at": row.get("analyzed_at").isoformat() if row.get("analyzed_at") else None,
        }
        for row in rows
    ]
