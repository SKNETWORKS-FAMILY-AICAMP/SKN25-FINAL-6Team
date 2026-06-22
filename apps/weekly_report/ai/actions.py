"""Generate AI-recommended actions for the weekly report."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm
from common.observability.langfuse import observe_if_enabled
from utils.labels import translate_value
from weekly_report_langfuse import link_weekly_report_trace


class ActionItem(BaseModel):
    rank: int = Field(description="Priority rank starting at 1")
    category: str = Field(description="Action category")
    action: str = Field(description="Concrete next action")
    reason: str = Field(description="Evidence-backed reason")


class AiRecommendedActions(BaseModel):
    headline: str = Field(description="One-line summary headline for this week")
    actions: list[ActionItem] = Field(description="Three to five recommended actions")


_SYSTEM_PROMPT = (
    "당신은 게임 고객지원 조직의 운영 분석가다.\n"
    "주어진 데이터만 사용해서 다음 주 운영 액션을 제안하라.\n"
    "모든 headline, category, action, reason 값은 반드시 한국어로 작성하라.\n"
    "JSON 키 이름은 그대로 유지하고 값만 한국어로 채워라.\n"
    "마케팅 또는 프로모션 관련 제안을 최소 1개 포함하라.\n"
    "입력에 없는 근거는 만들지 마라."
)
_FALLBACK_HEADLINE = "AI 권장 액션을 생성하지 못했습니다."
_FALLBACK_ACTION = "LLM 설정을 확인한 뒤 보고서를 다시 실행하세요."


def _category_label(value: Any) -> str:
    return str(translate_value(value, key="category"))


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "headline": _FALLBACK_HEADLINE,
        "actions": [
            {
                "rank": 1,
                "category": "시스템",
                "action": _FALLBACK_ACTION,
                "reason": reason,
            }
        ],
    }


def is_fallback_ai_actions(payload: dict[str, Any]) -> bool:
    headline = str(payload.get("headline") or "").strip()
    if headline == _FALLBACK_HEADLINE:
        return True

    actions = payload.get("actions") or []
    if not isinstance(actions, list) or not actions:
        return False

    first = actions[0]
    if not isinstance(first, dict):
        return False
    return str(first.get("action") or "").strip() == _FALLBACK_ACTION


def _build_user_prompt(report_payload: dict[str, Any]) -> str:
    summary = report_payload.get("summary", {})
    total_count = summary.get("total_count") or summary.get("analysis_count", 0)
    prev_total = summary.get("prev_total", 0) or 0
    pct_change = (total_count - prev_total) / prev_total if prev_total > 0 else 0.0

    anomaly = report_payload.get("anomaly_section", {})
    spike_alerts_raw = report_payload.get("spike_alerts", {})
    critical_hours: list[Any] = anomaly.get("critical_hours") or [
        item["hour"]
        for item in spike_alerts_raw.get("hourly", [])
        if item.get("level") == "critical"
    ]
    critical_categories: list[Any] = anomaly.get("critical_categories") or [
        item["category"]
        for item in spike_alerts_raw.get("by_category", [])
        if item.get("level") == "critical"
    ]
    if critical_hours or critical_categories:
        parts: list[str] = []
        if critical_hours:
            parts.append(f"집중 시간대 {critical_hours}")
        if critical_categories:
            translated_categories = [_category_label(category) for category in critical_categories]
            parts.append(f"집중 카테고리 {translated_categories}")
        critical_items = " / ".join(parts)
    else:
        critical_items = "없음"

    cat_dist_raw = report_payload.get("category_distribution", {})
    if isinstance(cat_dist_raw, list):
        cat_dist_str = ", ".join(
            f"{_category_label(item.get('label'))} {item['value']}건" for item in cat_dist_raw[:5]
        )
    else:
        cat_dist_str = ", ".join(
            f"{_category_label(k)} {v}건" for k, v in list(cat_dist_raw.items())[:5]
        )

    top5: list[Any] = report_payload.get("top5_improvements", [])
    top3 = top5[:3]
    if top3 and isinstance(top3[0], dict):
        top3_str = ", ".join(
            f"{_category_label(item.get('category', '?'))} ({item.get('count', 0)}건, {item.get('improvement_type', '')})"
            for item in top3
        )
    else:
        top3_str = "데이터 없음"

    return (
        "[주간 데이터]\n"
        f"- 전체 문의 수: {total_count}건 (전주 대비 {pct_change:+.1%})\n"
        f"- 주요 급증 구간: {critical_items}\n"
        f"- 카테고리 분포: {cat_dist_str}\n"
        f"- 개선 요청 상위 3개: {top3_str}\n\n"
        "이 데이터를 바탕으로 다음 주에 실행할 구체적인 운영 액션 3~5개를 제안하라.\n"
        "각 액션에는 반드시 데이터에 근거한 명시적 사유를 포함하라.\n"
        "마케팅 또는 프로모션 제안을 최소 1개 포함하라.\n"
        "category 값도 한국어로 작성하라.\n\n"
        'Return JSON only: {"headline":"...", "actions":[{"rank":1, "category":"...", "action":"...", "reason":"..."}]}'
    )


@observe_if_enabled(
    name="weekly_report_generate_ai_actions",
    as_type="generation",
    tags=["weekly-report", "feature:ai-actions"],
)
def generate_ai_actions(report_payload: dict[str, Any]) -> dict[str, Any]:
    link_weekly_report_trace(
        report_payload,
        tags=["weekly-report", "feature:ai-actions"],
        input_payload={
            "summary": report_payload.get("summary"),
            "top5_improvements_count": len(report_payload.get("top5_improvements", [])),
            "spike_alerts_keys": sorted((report_payload.get("spike_alerts") or {}).keys()),
        },
        top_requests_count=len(report_payload.get("top5_improvements", [])),
        alerts_count=sum(
            len((report_payload.get("spike_alerts") or {}).get(key, []))
            for key in ("hourly", "daily", "monthly")
        ),
    )

    if not _llm_available():
        result = _fallback("LLM 설정이 없습니다.")
        link_weekly_report_trace(
            result,
            tags=["weekly-report", "feature:ai-actions"],
            output_payload=result,
            status="fallback",
        )
        return result

    user_prompt = _build_user_prompt(report_payload)

    try:
        response = invoke_structured_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=AiRecommendedActions,
        )
    except Exception as exc:  # noqa: BLE001
        result = _fallback(f"LLM 생성 실패: {exc}")
        link_weekly_report_trace(
            result,
            tags=["weekly-report", "feature:ai-actions"],
            output_payload=result,
            status="fallback",
        )
        return result

    result = response.model_dump()
    link_weekly_report_trace(
        result,
        tags=["weekly-report", "feature:ai-actions"],
        output_payload=result,
        status="success",
    )
    return result
