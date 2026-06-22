"""Generate AI-recommended actions for the weekly report."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_weekly_report_trace


class ActionItem(BaseModel):
    rank: int = Field(description="Priority rank starting at 1")
    category: str = Field(description="Action category")
    action: str = Field(description="Concrete next action")
    reason: str = Field(description="Evidence-backed reason")


class AiRecommendedActions(BaseModel):
    headline: str = Field(description="One-line summary headline for this week")
    actions: list[ActionItem] = Field(description="Three to five recommended actions")


_SYSTEM_PROMPT = (
    "You are an operations analyst for a game customer-support organization.\n"
    "Use only the provided data to suggest concrete next-week actions.\n"
    "Include at least one marketing or promotion suggestion.\n"
    "Do not invent evidence that is not present in the input."
)
_FALLBACK_HEADLINE = "AI recommended actions could not be generated."


def _llm_available() -> bool:
    return bool(os.environ.get("LLM_MODEL") and os.environ.get("LLM_API_KEY"))


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "headline": _FALLBACK_HEADLINE,
        "actions": [
            {
                "rank": 1,
                "category": "시스템",
                "action": "Check the LLM configuration and run the report again.",
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
    return str(first.get("action") or "").strip() == "Check the LLM configuration and run the report again."


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
            parts.append(f"hours {critical_hours}")
        if critical_categories:
            parts.append(f"categories {critical_categories}")
        critical_items = " / ".join(parts)
    else:
        critical_items = "none"

    cat_dist_raw = report_payload.get("category_distribution", {})
    if isinstance(cat_dist_raw, list):
        cat_dist_str = ", ".join(
            f"{item['label']} {item['value']} cases" for item in cat_dist_raw[:5]
        )
    else:
        cat_dist_str = ", ".join(f"{k} {v} cases" for k, v in list(cat_dist_raw.items())[:5])

    top5: list[Any] = report_payload.get("top5_improvements", [])
    top3 = top5[:3]
    if top3 and isinstance(top3[0], dict):
        top3_str = ", ".join(
            f"{item.get('category', '?')} ({item.get('count', 0)} cases, {item.get('improvement_type', '')})"
            for item in top3
        )
    else:
        top3_str = "no data"

    return (
        "[Weekly data]\n"
        f"- Total inquiries: {total_count} ({pct_change:+.1%} vs previous week)\n"
        f"- Critical spikes: {critical_items}\n"
        f"- Category distribution: {cat_dist_str}\n"
        f"- Top 3 improvement requests: {top3_str}\n\n"
        "Based on this data, suggest 3 to 5 concrete operational actions for next week.\n"
        "Each action must include an explicit reason grounded in the data.\n"
        "Include at least one marketing suggestion.\n\n"
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
        result = _fallback("Missing LLM configuration.")
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
        result = _fallback(f"LLM generation failed: {exc}")
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
