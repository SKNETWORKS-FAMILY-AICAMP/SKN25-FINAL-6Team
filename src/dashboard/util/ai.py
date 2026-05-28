"""LLM-powered interpretation helpers for dashboard summaries."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langsmith import traceable
from pydantic import BaseModel, Field

from src.common.llm.client import invoke_structured_llm


DashboardPage = Literal["overview", "risk", "quality", "weekly_report"]


class InterpretationPayload(BaseModel):
    headline: str = Field(description="One short Korean headline for the current page.")
    summary: str = Field(description="A concise Korean summary interpreting the page as a whole.")
    bullets: list[str] = Field(default_factory=list, description="Three to five Korean bullet insights.")
    actions: list[str] = Field(default_factory=list, description="Two or three Korean action suggestions for operators.")


class ReviewRowInterpretationItem(BaseModel):
    analysis_id: int | None = Field(default=None, description="Analysis row identifier.")
    ticket_id: int | None = Field(default=None, description="Ticket identifier.")
    interpretation: str = Field(description="One concise Korean interpretation for this single row.")


class ReviewRowInterpretationPayload(BaseModel):
    items: list[ReviewRowInterpretationItem] = Field(default_factory=list, description="Row-by-row Korean interpretations.")


def _langsmith_tracing_enabled() -> bool:
    tracing_flag = (os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2") or "").strip().lower()
    return tracing_flag in {"1", "true", "yes", "on"} and bool(os.environ.get("LANGSMITH_API_KEY", "").strip())


def _traceable_if_enabled(*, name: str, tags: list[str]):
    def decorator(func):
        if not _langsmith_tracing_enabled():
            return func
        return traceable(name=name, tags=tags)(func)

    return decorator


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _system_prompt(page: DashboardPage) -> str:
    page_map = {
        "overview": "운영 현황",
        "risk": "위험 신호",
        "quality": "답변 품질",
        "weekly_report": "주간 보고서",
    }
    return (
        "너는 게임 운영 대시보드를 읽고 운영 담당자에게 쉬운 한국어로 설명하는 분석가다. "
        f"이번 입력은 '{page_map[page]}' 페이지 데이터다. "
        "영문 약어, DB 컬럼명, 테이블 이름을 그대로 쓰지 말고 뜻을 풀어 설명한다. "
        "수치를 단순 나열하지 말고, 흐름과 우선순위를 해석하고 운영자가 바로 이해할 수 있게 쓴다. "
        "불확실한 사실을 지어내지 말고 입력 데이터에 근거해서만 답한다. "
        "bullets는 3개에서 5개, actions는 2개에서 3개로 제한한다."
    )


def _fallback(page: DashboardPage, reason: str) -> dict[str, Any]:
    titles = {
        "overview": "AI 해석을 아직 만들지 못했습니다.",
        "risk": "AI 위험 해석을 아직 만들지 못했습니다.",
        "quality": "AI 품질 해석을 아직 만들지 못했습니다.",
        "weekly_report": "AI 주간 해석을 아직 만들지 못했습니다.",
    }
    return {
        "headline": titles[page],
        "summary": "모델 설정이 없거나 호출에 실패해 자동 해석을 준비하지 못했습니다.",
        "bullets": [reason],
        "actions": ["LLM 설정을 확인한 뒤 다시 불러와 주세요."],
    }


def _trim_rows(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    return rows[:limit]


def _compact_payload(page: DashboardPage, payload: dict[str, Any]) -> dict[str, Any]:
    if page == "overview":
        return {
            "window": payload.get("window", {}),
            "ticket_counts": payload.get("ticket_counts", {}),
            "response_metrics": payload.get("response_metrics", {}),
            "coverage_metrics": payload.get("coverage_metrics", {}),
            "source_distribution": payload.get("source_distribution", []),
            "status_distribution": payload.get("status_distribution", []),
            "routing_distribution": payload.get("routing_distribution", []),
            "old_pending_count": payload.get("old_pending_count", 0),
            "recent_tickets": _trim_rows(payload.get("recent_tickets", [])),
        }
    if page == "risk":
        return {
            "window": payload.get("window", {}),
            "analysis_risk_distribution": payload.get("analysis_risk_distribution", []),
            "sentiment_distribution": payload.get("sentiment_distribution", []),
            "insight_risk_distribution": payload.get("insight_risk_distribution", []),
            "pattern_risk_distribution": payload.get("pattern_risk_distribution", []),
            "safety_score_summary": payload.get("safety_score_summary", {}),
            "safety_alerts": payload.get("safety_alerts", {}),
            "high_risk_tickets": _trim_rows(payload.get("high_risk_tickets", [])),
            "safety_breach_candidates": _trim_rows(payload.get("safety_breach_candidates", [])),
        }
    if page == "quality":
        return {
            "window": payload.get("window", {}),
            "draft_summary": payload.get("draft_summary", {}),
            "evidence_summary": payload.get("evidence_summary", {}),
            "safety_summary": payload.get("safety_summary", {}),
            "final_response_summary": payload.get("final_response_summary", {}),
            "notification_summary": payload.get("notification_summary", []),
            "coverage_metrics": payload.get("coverage_metrics", {}),
            "quality_candidates": _trim_rows(payload.get("quality_candidates", [])),
            "notification_failures": _trim_rows(payload.get("notification_failures", [])),
        }
    return {
        "title": payload.get("title"),
        "window": payload.get("window", {}),
        "previous_window": payload.get("previous_window", {}),
        "summary": payload.get("summary", {}),
        "comparisons": payload.get("comparisons", {}),
        "category_distribution": payload.get("category_distribution", []),
        "responder_distribution": payload.get("responder_distribution", []),
        "risk_distribution": payload.get("risk_distribution", []),
        "sentiment_distribution": payload.get("sentiment_distribution", []),
        "routing_distribution": payload.get("routing_distribution", []),
        "review_rows": _trim_rows(payload.get("review_rows", [])),
    }


@_traceable_if_enabled(name="generate_dashboard_interpretation", tags=["dashboard", "interpretation"])
def generate_dashboard_interpretation(page: DashboardPage, payload: dict[str, Any]) -> dict[str, Any]:
    """Return an LLM-generated interpretation for a dashboard page."""

    if not _llm_available():
        return _fallback(page, "현재 환경에 LLM 모델 설정이 없어 AI 해석을 생략했습니다.")

    compact_payload = _compact_payload(page, payload)
    user_prompt = (
        "다음 JSON은 대시보드 한 페이지의 핵심 데이터다.\n"
        "운영 담당자가 바로 이해할 수 있도록 페이지 전체를 종합 해석해라.\n"
        "특정 수치가 높거나 낮은 이유를 추정할 때는 반드시 입력 데이터에 근거한 수준으로만 설명해라.\n"
        "JSON:\n"
        f"{json.dumps(compact_payload, ensure_ascii=False, default=str, indent=2)}"
    )
    try:
        response = invoke_structured_llm(
            system_prompt=_system_prompt(page),
            user_prompt=user_prompt,
            response_model=InterpretationPayload,
        )
    except Exception as exc:  # noqa: BLE001 - do not break dashboard UI on AI failure
        return _fallback(page, f"AI 해석 호출에 실패했습니다: {exc}")
    return response.model_dump()


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
    """Generate concise Korean interpretations for weekly report review rows."""

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
    except Exception:
        return [
            {
                "analysis_id": row.get("analysis_id"),
                "ticket_id": row.get("ticket_id"),
                "interpretation": _fallback_row_interpretation(row),
            }
            for row in rows
        ]

    by_key = {
        (item.analysis_id, item.ticket_id): item.interpretation
        for item in response.items
    }
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
