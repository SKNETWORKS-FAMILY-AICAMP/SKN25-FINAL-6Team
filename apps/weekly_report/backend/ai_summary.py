"""주간 리포트 AI 권장 액션 생성.

수신자: 기획팀
출력: headline + actions 3~5개 (각 액션에 근거 수치 포함, 마케팅 시사점 1개 이상)
근거: Sánchez Pérez et al. (2025) NAACL-HLT — DB 집계 → LLM → 텍스트 인사이트 파이프라인
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm


class ActionItem(BaseModel):
    rank: int = Field(description="액션 우선순위 번호 (1부터 시작)")
    category: str = Field(description="해당 액션의 대상 카테고리 또는 분야")
    action: str = Field(description="즉시 실행 가능한 구체적 액션")
    reason: str = Field(description="근거 수치를 포함한 한국어 이유")


class AiRecommendedActions(BaseModel):
    headline: str = Field(description="이번 주 운영 현황을 한 문장으로 요약한 한국어 헤드라인")
    actions: list[ActionItem] = Field(description="기획팀을 위한 다음 주 운영 액션 3~5개")


_SYSTEM_PROMPT = (
    "당신은 게임 서비스 CS 데이터를 분석하는 운영 전략 어시스턴트입니다.\n"
    "수신자는 기획팀이며, 데이터 기반으로 다음 주에 즉시 실행 가능한 액션을 제안해야 합니다.\n"
    "마케팅 시사점을 반드시 1개 이상 포함하세요.\n"
    "반드시 제공된 수치 데이터만 근거로 사용하고, 외부 추측을 포함하지 마세요."
)


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "headline": "AI 권장 액션을 생성하지 못했습니다.",
        "actions": [
            {
                "rank": 1,
                "category": "시스템",
                "action": "LLM 설정을 확인한 뒤 다시 실행하세요.",
                "reason": reason,
            }
        ],
    }


def _build_user_prompt(report_payload: dict[str, Any]) -> str:
    summary = report_payload.get("summary", {})
    total_count = summary.get("total_count") or summary.get("analysis_count", 0)
    prev_total = summary.get("prev_total", 0) or 0
    pct_change = (total_count - prev_total) / prev_total if prev_total > 0 else 0.0

    # 폭증 감지 요약
    anomaly = report_payload.get("anomaly_section", {})
    spike_alerts_raw = report_payload.get("spike_alerts", {})
    critical_hours: list = anomaly.get("critical_hours") or [
        item["hour"]
        for item in spike_alerts_raw.get("hourly", [])
        if item.get("level") == "critical"
    ]
    critical_categories: list = anomaly.get("critical_categories") or [
        item["category"]
        for item in spike_alerts_raw.get("by_category", [])
        if item.get("level") == "critical"
    ]
    if critical_hours or critical_categories:
        parts = []
        if critical_hours:
            parts.append(f"시간대 {critical_hours}")
        if critical_categories:
            parts.append(f"카테고리 {critical_categories}")
        critical_items = " / ".join(parts)
    else:
        critical_items = "없음"

    # 카테고리 분포
    cat_dist_raw = report_payload.get("category_distribution", {})
    if isinstance(cat_dist_raw, list):
        cat_dist_str = ", ".join(
            f"{item['label']} {item['value']}건" for item in cat_dist_raw[:5]
        )
    else:
        cat_dist_str = ", ".join(f"{k} {v}건" for k, v in list(cat_dist_raw.items())[:5])

    # Top 3 개선 요청
    top5: list = report_payload.get("top5_improvements", [])
    top3 = top5[:3]
    if top3 and isinstance(top3[0], dict):
        top3_str = ", ".join(
            f"{item.get('category', '?')}({item.get('count', 0)}건, {item.get('improvement_type', '')})"
            for item in top3
        )
    else:
        top3_str = "데이터 없음"

    return (
        "[이번 주 데이터]\n"
        f"- 총 문의: {total_count}건 (전주 대비 {pct_change:+.1%})\n"
        f"- 폭증 감지: {critical_items}\n"
        f"- 카테고리 분포: {cat_dist_str}\n"
        f"- 유저 개선 요청 Top 3: {top3_str}\n\n"
        "위 데이터를 근거로 기획팀을 위한 다음 주 운영 액션 3~5개를 제안하라.\n"
        "각 액션에 근거 수치를 반드시 명시하라.\n"
        "마케팅 시사점을 1개 이상 포함하라.\n\n"
        '출력 형식(JSON만 반환):\n'
        '{"headline": "...", "actions": [{"rank":1, "category":"...", "action":"...", "reason":"..."}]}'
    )


def generate_ai_actions(report_payload: dict[str, Any]) -> dict[str, Any]:
    """report_payload 를 받아 기획팀용 AI 권장 액션을 반환한다.

    LLM을 사용할 수 없으면 fallback 텍스트를 반환한다.
    """
    if not _llm_available():
        return _fallback("현재 환경에 LLM 모델 설정이 없어 AI 권장 액션을 생략했습니다.")

    user_prompt = _build_user_prompt(report_payload)

    try:
        response = invoke_structured_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=AiRecommendedActions,
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback(f"AI 권장 액션 호출에 실패했습니다: {exc}")

    return response.model_dump()
