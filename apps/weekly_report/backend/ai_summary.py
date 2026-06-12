"""주간 리포트 AI 요약 + 권장 액션 생성."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm


class WeeklyReportSummary(BaseModel):
    headline: str = Field(description="이번 주 운영 현황을 한 문장으로 요약한 한국어 헤드라인.")
    summary: str = Field(description="주간 지표, 요청 현황, 급증 알림을 종합한 한국어 요약 (3~5문장).")
    bullets: list[str] = Field(default_factory=list, description="운영 담당자가 바로 볼 한국어 핵심 인사이트 3~5개.")
    actions: list[str] = Field(default_factory=list, description="이번 주 즉시 조치가 필요한 한국어 권장 액션 2~3개.")


_SYSTEM_PROMPT = (
    "너는 게임 운영팀 주간 리포트를 분석하는 전문가다. "
    "주어진 JSON 데이터(주간 지표, 유저 요청 Top5, 급증 알림)를 바탕으로 "
    "운영 담당자가 즉시 이해할 수 있는 한국어 요약을 작성한다. "
    "수치를 단순 나열하지 말고 흐름과 우선순위를 해석한다. "
    "불확실한 사실을 지어내지 말고, 입력 데이터에 근거해서만 답한다. "
    "'ticket', '티켓' 대신 '문의' 또는 '문의 건'을 사용한다. "
    "bullets 3~5개, actions 2~3개로 제한한다."
)


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "headline": "AI 주간 해석을 아직 만들지 못했습니다.",
        "summary": "모델 설정이 없거나 호출에 실패해 자동 해석을 준비하지 못했습니다.",
        "bullets": [reason],
        "actions": ["LLM 설정을 확인한 뒤 다시 불러와 주세요."],
    }


def generate(
    metrics: dict[str, Any],
    requests: dict[str, Any],
    alerts: dict[str, Any],
) -> dict[str, Any]:
    """metrics / requests / alerts 를 종합해 AI 요약을 반환한다.

    LLM을 사용할 수 없으면 fallback 텍스트를 반환한다.
    """
    if not _llm_available():
        return _fallback("현재 환경에 LLM 모델 설정이 없어 AI 해석을 생략했습니다.")

    compact = {
        "weekly_metrics": {
            "total_tickets": metrics.get("total_tickets"),
            "response_rate": metrics.get("response_rate"),
            "analysis_coverage_rate": metrics.get("analysis_coverage_rate"),
            "draft_coverage_rate": metrics.get("draft_coverage_rate"),
            "draft_ticket_rate": metrics.get("draft_ticket_rate"),
            "final_response_ticket_rate": metrics.get("final_response_ticket_rate"),
            "draft_count": metrics.get("draft_count"),
            "safety_check_count": metrics.get("safety_check_count"),
            "category_counts": metrics.get("category_counts", [])[:5],
        },
        "top_requests": requests,
        "spike_alerts": {
            "critical_hourly": [a for a in alerts.get("hourly", []) if a.get("level") == "critical"][:3],
            "critical_daily": [a for a in alerts.get("daily", []) if a.get("level") in {"critical", "warning"}][:3],
            "critical_category": [a for a in alerts.get("by_category", []) if a.get("level") in {"critical", "warning"}][:3],
        },
    }

    user_prompt = (
        "다음 JSON은 이번 주 운영 주요 데이터다.\n"
        "운영 담당자가 바로 이해할 수 있도록 종합 해석해라.\n"
        "JSON:\n"
        f"{json.dumps(compact, ensure_ascii=False, default=str, indent=2)}"
    )

    try:
        response = invoke_structured_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=WeeklyReportSummary,
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback(f"AI 해석 호출에 실패했습니다: {exc}")

    return response.model_dump()
