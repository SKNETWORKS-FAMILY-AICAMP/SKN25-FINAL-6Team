"""개별 문의 행 AI 해석 생성 — 주간 보고서 우선 확인 행 전용."""

from __future__ import annotations

import json
import os
from typing import Any

from langsmith import traceable
from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm


class ReviewRowInterpretationItem(BaseModel):
    analysis_id: int | None = Field(default=None, description="Analysis row identifier.")
    ticket_id: int | None = Field(default=None, description="Ticket identifier.")
    interpretation: str = Field(description="One concise Korean interpretation for this single row.")


class ReviewRowInterpretationPayload(BaseModel):
    items: list[ReviewRowInterpretationItem] = Field(
        default_factory=list, description="Row-by-row Korean interpretations."
    )


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _langsmith_tracing_enabled() -> bool:
    tracing_flag = (os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2") or "").strip().lower()
    return tracing_flag in {"1", "true", "yes", "on"} and bool(os.environ.get("LANGSMITH_API_KEY", "").strip())


def _traceable_if_enabled(*, name: str, tags: list[str]):
    def decorator(func):
        if not _langsmith_tracing_enabled():
            return func
        return traceable(name=name, tags=tags)(func)
    return decorator


def _fallback_row_interpretation(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "제목 없는 문의").strip()
    category = str(row.get("category") or "분류 미확인").strip()
    risk = str(row.get("risk_level") or "위험도 미확인").strip()
    next_step = str(row.get("routing_target") or "후속 처리 미정").strip()
    sentiment = str(row.get("sentiment") or "").strip()
    sentiment_text = f", 이용자 반응은 {sentiment}" if sentiment else ""
    return f"'{title}' 문의는 {category} 유형으로 보이며 위험도는 {risk}{sentiment_text}이고, 다음 처리는 {next_step}로 잡혀 있어 지금 확인이 필요합니다."


@_traceable_if_enabled(name="generate_review_row_interpretations", tags=["dashboard", "weekly_report"])
def generate_review_row_interpretations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    if not _llm_available():
        return [
            {
                "analysis_id": row.get("analysis_id"),
                "ticket_id": row.get("ticket_id"),
                "interpretation": _fallback_row_interpretation(row),
            }
            for row in rows
        ]

    compact_rows = [
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
            "pattern_risk_level": row.get("pattern_risk_level"),
            "analyzed_at": row.get("analyzed_at"),
        }
        for row in rows
    ]
    user_prompt = (
        "다음 JSON은 주간 보고서에서 우선 확인 대상으로 뽑힌 문의 행 목록이다.\n"
        "각 행마다 한 줄짜리 한국어 해석을 만들어라.\n"
        "기존 summary를 베끼지 말고, 제목, 문의 분류, 위험도, 이용자 반응, 다음 처리 방향을 종합해서 운영자가 바로 이해할 수 있게 새로 써라.\n"
        "각 해석은 한 문장으로 40자 이상 110자 이하를 목표로 하고, 왜 지금 봐야 하는지 드러나게 써라.\n"
        "JSON:\n"
        f"{json.dumps(compact_rows, ensure_ascii=False, default=str, indent=2)}"
    )
    try:
        response = invoke_structured_llm(
            system_prompt=(
                "너는 게임 운영팀 주간 보고서를 쓰는 분석가다. "
                "한 행에 대한 해석만 쓰고, 영문 키나 DB 컬럼명을 그대로 쓰지 않는다. "
                "과장하지 말고 입력 행의 정보만으로 우선 확인 이유를 풀어서 설명한다."
            ),
            user_prompt=user_prompt,
            response_model=ReviewRowInterpretationPayload,
        )
    except Exception:  # noqa: BLE001
        return [
            {
                "analysis_id": row.get("analysis_id"),
                "ticket_id": row.get("ticket_id"),
                "interpretation": _fallback_row_interpretation(row),
            }
            for row in rows
        ]

    by_key = {(item.analysis_id, item.ticket_id): item.interpretation for item in response.items}
    return [
        {
            "analysis_id": row.get("analysis_id"),
            "ticket_id": row.get("ticket_id"),
            "interpretation": by_key.get(
                (row.get("analysis_id"), row.get("ticket_id")),
                _fallback_row_interpretation(row),
            ),
        }
        for row in rows
    ]
