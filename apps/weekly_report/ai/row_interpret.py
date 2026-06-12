"""개별 문의 행 AI 해석 생성 — 주간 보고서 우선 확인 행 전용."""

from __future__ import annotations

import json
import os
from typing import Any

from langsmith import traceable
from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm


class ReviewRowInterpretationItem(BaseModel):
    # analysis_id와 ticket_id 모두 Optional인 이유:
    # LLM이 반환한 JSON에서 어느 한쪽 키가 누락되더라도 역매핑 단계에서 fallback으로 처리하기 위함.
    analysis_id: int | None = Field(default=None, description="Analysis row identifier.")
    ticket_id: int | None = Field(default=None, description="Ticket identifier.")
    interpretation: str = Field(description="One concise Korean interpretation for this single row.")


class ReviewRowInterpretationPayload(BaseModel):
    # LLM 응답 전체를 단일 객체로 파싱해 항목별 리스트로 접근하기 위한 래퍼.
    items: list[ReviewRowInterpretationItem] = Field(
        default_factory=list, description="Row-by-row Korean interpretations."
    )


def _llm_available() -> bool:
    # 모델명과 API 키 둘 다 있어야 실제 호출 가능 — 어느 한쪽만 있으면 호출해도 실패하므로 둘 다 확인.
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _langsmith_tracing_enabled() -> bool:
    # LangChain 구버전 환경변수(LANGCHAIN_TRACING_V2)와 신버전(LANGSMITH_TRACING) 모두 지원.
    tracing_flag = (os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2") or "").strip().lower()
    # API 키가 없으면 tracing 플래그가 on이어도 실제로 전송할 수 없으므로 같이 확인.
    return tracing_flag in {"1", "true", "yes", "on"} and bool(os.environ.get("LANGSMITH_API_KEY", "").strip())


def _traceable_if_enabled(*, name: str, tags: list[str]):
    """LangSmith 트레이싱이 활성화된 경우에만 @traceable 데코레이터를 적용하는 팩토리.

    트레이싱이 꺼진 환경(로컬 개발, 테스트)에서는 원본 함수를 그대로 반환해
    LangSmith 의존성 없이도 동작하도록 한다.
    """
    def decorator(func):
        if not _langsmith_tracing_enabled():
            return func
        return traceable(name=name, tags=tags)(func)
    return decorator


def _fallback_row_interpretation(row: dict[str, Any]) -> str:
    """LLM 호출 불가 또는 실패 시 DB 데이터만으로 한 줄 해석을 구성한다.

    필드가 None이나 빈 문자열이면 안전한 기본값으로 대체해 빈 문자열이 PDF에 노출되지 않게 한다.
    """
    title = str(row.get("title") or "제목 없는 문의").strip()
    category = str(row.get("category") or "분류 미확인").strip()
    risk = str(row.get("risk_level") or "위험도 미확인").strip()
    next_step = str(row.get("routing_target") or "후속 처리 미정").strip()
    sentiment = str(row.get("sentiment") or "").strip()
    # 감정 정보가 있을 때만 문장에 포함해 불필요한 "이용자 반응은 " 문구가 생기지 않게 한다.
    sentiment_text = f", 이용자 반응은 {sentiment}" if sentiment else ""
    return f"'{title}' 문의는 {category} 유형으로 보이며 위험도는 {risk}{sentiment_text}이고, 다음 처리는 {next_step}로 잡혀 있어 지금 확인이 필요합니다."


@_traceable_if_enabled(name="generate_review_row_interpretations", tags=["dashboard", "weekly_report"])
def generate_review_row_interpretations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """우선 확인 행 목록을 받아 각 행에 대한 한 줄 한국어 해석을 반환한다.

    LLM을 사용할 수 없으면 _fallback_row_interpretation으로 규칙 기반 해석을 생성한다.
    LLM 호출이 실패해도 동일한 fallback으로 보고서 생성이 중단되지 않는다.
    """
    if not rows:
        return []

    # LLM 설정이 없으면 전 행을 즉시 fallback으로 처리해 불필요한 API 연결 시도를 하지 않는다.
    if not _llm_available():
        return [
            {
                "analysis_id": row.get("analysis_id"),
                "ticket_id": row.get("ticket_id"),
                "interpretation": _fallback_row_interpretation(row),
            }
            for row in rows
        ]

    # LLM 프롬프트에 전달할 컬럼만 추려 토큰 비용을 줄인다.
    # nickname, inquiry_created_at 등 해석에 불필요한 필드는 제외한다.
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
        # 네트워크 오류, 파싱 실패, 타임아웃 등 어떤 예외도 보고서 전체를 중단시키지 않는다.
        return [
            {
                "analysis_id": row.get("analysis_id"),
                "ticket_id": row.get("ticket_id"),
                "interpretation": _fallback_row_interpretation(row),
            }
            for row in rows
        ]

    # (analysis_id, ticket_id) 쌍을 키로 사용해 LLM 응답을 원본 행에 빠르게 매핑한다.
    # 한쪽 ID만 일치해도 잘못된 행과 연결될 수 있으므로 두 값을 묶어 복합 키로 쓴다.
    by_key = {(item.analysis_id, item.ticket_id): item.interpretation for item in response.items}
    return [
        {
            "analysis_id": row.get("analysis_id"),
            "ticket_id": row.get("ticket_id"),
            # LLM이 해당 행의 해석을 반환하지 않았으면 fallback으로 채운다.
            "interpretation": by_key.get(
                (row.get("analysis_id"), row.get("ticket_id")),
                _fallback_row_interpretation(row),
            ),
        }
        for row in rows
    ]
