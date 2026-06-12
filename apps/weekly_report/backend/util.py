"""계산·포매팅·AI 해석 유틸 — util/ai.py + util/metrics.py + util/text.py 합본."""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# util/metrics.py 출처
# ──────────────────────────────────────────────────────────────────────────────
import json
import os
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Literal

MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 30


def clamp_days(days: int | float | str, *, min_days: int = MIN_DAYS, max_days: int = MAX_DAYS) -> int:
    value = int(days)
    return max(min_days, min(value, max_days))


def build_window(days: int, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    days = clamp_days(days)
    return {
        "days": days,
        "window_start": current - timedelta(days=days),
        "window_end": current,
    }


def rate(numerator: int | float | None, denominator: int | float | None) -> float:
    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


def safe_average(values: list[int | float | None]) -> float | None:
    filtered = [float(v) for v in values if v is not None]
    if not filtered:
        return None
    return float(mean(filtered))


def _window_payload(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "days": int(window["days"]),
        "window_start": window["window_start"].isoformat(),
        "window_end": window["window_end"].isoformat(),
    }


def build_overview_payload(
    *,
    window: dict[str, Any],
    raw_counts: dict[str, Any],
    response_metrics: dict[str, Any],
    source_distribution: list[dict[str, Any]],
    status_distribution: list[dict[str, Any]],
    routing_distribution: list[dict[str, Any]],
    recent_tickets: list[dict[str, Any]],
) -> dict[str, Any]:
    total_tickets = int(raw_counts.get("total_tickets") or 0)
    pending_tickets = int(raw_counts.get("pending_tickets") or 0)
    closed_tickets = int(raw_counts.get("closed_tickets") or 0)
    today_tickets = int(raw_counts.get("today_tickets") or 0)
    old_pending_count = int(raw_counts.get("old_pending_count") or 0)
    responded_tickets = int(response_metrics.get("responded_tickets") or 0)
    draft_tickets = int(response_metrics.get("draft_tickets") or 0)
    analyzed_tickets = int(response_metrics.get("analyzed_tickets") or 0)

    return {
        "window": _window_payload(window),
        "ticket_counts": {
            "total": total_tickets,
            "pending": pending_tickets,
            "closed": closed_tickets,
            "today": today_tickets,
        },
        "response_metrics": {
            "response_rate": rate(responded_tickets, total_tickets),
            "draft_coverage_rate": rate(draft_tickets, total_tickets),
            "analysis_coverage_rate": rate(analyzed_tickets, total_tickets),
            "avg_response_latency_minutes": response_metrics.get("avg_response_latency_minutes"),
        },
        "coverage_metrics": {
            "response_rate": rate(responded_tickets, total_tickets),
            "draft_coverage_rate": rate(draft_tickets, total_tickets),
            "analysis_coverage_rate": rate(analyzed_tickets, total_tickets),
        },
        "source_distribution": source_distribution,
        "status_distribution": status_distribution,
        "routing_distribution": routing_distribution,
        "old_pending_count": old_pending_count,
        "recent_tickets": recent_tickets,
    }


def build_risk_payload(
    *,
    window: dict[str, Any],
    analysis_risk_distribution: list[dict[str, Any]],
    sentiment_distribution: list[dict[str, Any]],
    insight_risk_distribution: list[dict[str, Any]],
    pattern_risk_distribution: list[dict[str, Any]],
    safety_score_summary: dict[str, Any],
    high_risk_tickets: list[dict[str, Any]],
    safety_breach_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    avg_hallucination = safety_score_summary.get("avg_hallucination_score")
    avg_toxicity = safety_score_summary.get("avg_toxicity_score")
    avg_policy = safety_score_summary.get("avg_policy_violation_score")
    avg_factuality = safety_score_summary.get("avg_factuality_score")

    return {
        "window": _window_payload(window),
        "analysis_risk_distribution": analysis_risk_distribution,
        "sentiment_distribution": sentiment_distribution,
        "insight_risk_distribution": insight_risk_distribution,
        "pattern_risk_distribution": pattern_risk_distribution,
        "safety_score_summary": {
            "avg_hallucination_score": avg_hallucination,
            "avg_toxicity_score": avg_toxicity,
            "avg_policy_violation_score": avg_policy,
            "avg_factuality_score": avg_factuality,
            "safety_check_count": int(safety_score_summary.get("safety_check_count") or 0),
        },
        "safety_alerts": {
            "high_hallucination": (avg_hallucination or 0) >= 0.7,
            "high_toxicity": (avg_toxicity or 0) >= 0.7,
            "high_policy_violation": (avg_policy or 0) >= 0.7,
            "low_factuality": avg_factuality is not None and avg_factuality <= 0.3,
        },
        "high_risk_tickets": high_risk_tickets,
        "safety_breach_candidates": safety_breach_candidates,
    }


def build_quality_payload(
    *,
    window: dict[str, Any],
    ticket_summary: dict[str, Any],
    draft_summary: dict[str, Any],
    evidence_summary: dict[str, Any],
    safety_summary: dict[str, Any],
    final_response_summary: dict[str, Any],
    notification_summary: list[dict[str, Any]],
    quality_candidates: list[dict[str, Any]],
    notification_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    ticket_count = int(ticket_summary.get("ticket_count") or 0)
    draft_count = int(draft_summary.get("draft_count") or 0)
    evidence_linked_drafts = int(draft_summary.get("evidence_linked_drafts") or 0)
    final_response_count = int(final_response_summary.get("final_response_count") or 0)
    final_response_ticket_count = int(final_response_summary.get("final_response_ticket_count") or 0)
    evidence_count = int(evidence_summary.get("evidence_count") or 0)

    return {
        "window": _window_payload(window),
        "draft_summary": {
            "draft_count": draft_count,
            "draft_ticket_count": int(draft_summary.get("draft_ticket_count") or 0),
            "evidence_linked_drafts": evidence_linked_drafts,
            "avg_draft_latency_minutes": draft_summary.get("avg_draft_latency_minutes"),
        },
        "evidence_summary": {
            "evidence_count": evidence_count,
            "avg_relevance_score": evidence_summary.get("avg_relevance_score"),
            "avg_retrieval_rank": evidence_summary.get("avg_retrieval_rank"),
        },
        "safety_summary": {
            "avg_hallucination_score": safety_summary.get("avg_hallucination_score"),
            "avg_toxicity_score": safety_summary.get("avg_toxicity_score"),
            "avg_policy_violation_score": safety_summary.get("avg_policy_violation_score"),
            "avg_factuality_score": safety_summary.get("avg_factuality_score"),
            "safety_check_count": int(safety_summary.get("safety_check_count") or 0),
        },
        "final_response_summary": {
            "final_response_count": final_response_count,
            "final_response_ticket_count": final_response_ticket_count,
            "avg_final_latency_minutes": final_response_summary.get("avg_final_latency_minutes"),
        },
        "notification_summary": notification_summary,
        "coverage_metrics": {
            "draft_ticket_rate": rate(draft_summary.get("draft_ticket_count"), ticket_count),
            "evidence_attachment_rate": rate(evidence_linked_drafts, draft_count),
            "final_response_ticket_rate": rate(final_response_ticket_count, ticket_count),
        },
        "quality_candidates": quality_candidates,
        "notification_failures": notification_failures,
    }


# ──────────────────────────────────────────────────────────────────────────────
# util/ai.py 출처
# ──────────────────────────────────────────────────────────────────────────────
from langsmith import traceable
from pydantic import BaseModel, Field

from common.llm.client import invoke_structured_llm


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
        "'ticket', '티켓'이라는 표현 대신 '문의' 또는 '문의 건'을 사용한다. "
    )


def _ai_fallback(page: DashboardPage, reason: str) -> dict[str, Any]:
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
    if not _llm_available():
        return _ai_fallback(page, "현재 환경에 LLM 모델 설정이 없어 AI 해석을 생략했습니다.")

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
    except Exception as exc:  # noqa: BLE001
        return _ai_fallback(page, f"AI 해석 호출에 실패했습니다: {exc}")
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


# ──────────────────────────────────────────────────────────────────────────────
# util/text.py 출처
# ──────────────────────────────────────────────────────────────────────────────

COLUMN_LABELS: dict[str, str] = {
    "account_id": "계정 번호",
    "account_status": "계정 상태",
    "analysis_count": "분석 건수",
    "analysis_id": "분석 번호",
    "ai_row_interpretation": "AI 행 해석",
    "analyzed_at": "분석 시각",
    "avg_draft_latency_minutes": "초안 작성 평균 시간",
    "avg_final_latency_minutes": "최종 응답 평균 시간",
    "avg_response_latency_minutes": "첫 응답 평균 시간",
    "avg_relevance_score": "근거 관련성 평균",
    "avg_retrieval_rank": "근거 검색 순위 평균",
    "backlog_metrics": "백로그 지표",
    "category": "문의 분류",
    "channel": "채널",
    "checked_at": "점검 시각",
    "coaching_queue": "품질 코칭 큐",
    "coaching_reason": "품질 검토 사유",
    "column": "확인 항목",
    "created_at": "생성 시각",
    "critical_risk_count": "치명 위험 문의",
    "draft_id": "초안 번호",
    "drafts_without_evidence": "근거 없는 초안",
    "email": "이메일",
    "enriched_query": "정제된 문의 내용",
    "error_category": "실패 유형",
    "error_message": "실패 사유",
    "escalation_queue": "에스컬레이션 큐",
    "escalation_reason": "에스컬레이션 사유",
    "evidence_count": "근거 수",
    "evidence_id": "근거 번호",
    "evidence_linked_drafts": "근거 첨부 초안",
    "evidence_text": "근거 내용",
    "failure_distribution": "실패 분포",
    "factuality_score": "사실성 점수",
    "final_response_count": "최종 응답 수",
    "final_response_ticket_count": "최종 응답 완료 문의",
    "game_name": "게임명",
    "hallucination_score": "환각 위험 점수",
    "high_risk_count": "고위험 문의",
    "human_review_backlog_count": "사람 검토 대기",
    "human_review_count": "사람 검토 필요 문의",
    "inquiry_created_at": "접수 시각",
    "insight": "해석",
    "item_name": "아이템명",
    "label": "구분",
    "latest_analysis_id": "최신 분석 번호",
    "latest_draft_id": "최신 초안 번호",
    "latest_response_created_at": "최신 응답 시각",
    "latest_response_id": "최신 응답 번호",
    "message": "전송 내용",
    "metric": "수치",
    "negative_sentiment_count": "부정 반응 문의",
    "nickname": "이용자 닉네임",
    "notification_channel_distribution": "채널별 실패 분포",
    "notification_error_distribution": "실패 유형 분포",
    "notification_id": "알림 번호",
    "old_pending_count": "24시간 이상 대기 문의",
    "pattern_risk_level": "반복 패턴 위험도",
    "payment_id": "결제 번호",
    "pipeline_gaps": "파이프라인 누락",
    "policy_violation_score": "정책 위반 점수",
    "priority_tickets": "우선 처리 문의",
    "progression_level": "성장 단계",
    "quality_watch_rate": "품질 점검 비율",
    "queue_reason": "우선 처리 사유",
    "quantity": "수량",
    "raw_content": "원문 내용",
    "raw_query": "문의 원문",
    "refund_id": "환불 번호",
    "refund_reason": "환불 사유",
    "refund_status": "환불 상태",
    "relevance_score": "관련성 점수",
    "responded_within_24h_rate": "24시간 내 응답 비율",
    "responder_type": "응답 주체",
    "response_id": "응답 번호",
    "retry_count": "재시도 횟수",
    "retrieval_rank": "근거 검색 순위",
    "risk_hotspots": "위험 집중 구간",
    "risk_level": "위험도",
    "risk_summary": "위험 요약",
    "routing_target": "다음 처리",
    "safety_action": "안전 처리 결과",
    "safety_check_count": "안전 점검 수",
    "safety_reason": "안전 처리 사유",
    "sent_at": "전송 시각",
    "sentiment": "이용자 반응",
    "server_region": "서버 권역",
    "severity": "주의 수준",
    "sla_metrics": "응답 SLA",
    "source_id": "원본 번호",
    "source_type": "접수 경로",
    "status": "처리 상태",
    "summary": "요약",
    "ticket_count": "문의 수",
    "ticket_id": "문의 번호",
    "tickets_without_analysis": "분석 없는 문의",
    "tickets_without_draft": "초안 없는 문의",
    "tickets_without_response": "최종 응답 없는 문의",
    "title": "문의 제목",
    "toxicity_score": "독성 점수",
    "topic_keywords": "주요 키워드",
    "transaction_id": "거래 번호",
    "uid": "게임 계정 UID",
    "unanswered_rate": "미응답 비율",
    "urgent_unanswered_count": "긴급 미응답 문의",
    "user_id": "이용자 번호",
    "user_status": "이용자 상태",
    "value": "값",
    "voc_id": "VOC 번호",
    "voc_type": "VOC 유형",
}

VALUE_LABELS: dict[str, str] = {
    "all": "전체",
    "analysis": "분석",
    "analysis_coverage": "분석 완료 비율",
    "auto_reply": "자동 응답",
    "chat": "채팅",
    "closed": "처리 완료",
    "community": "커뮤니티",
    "completed": "완료",
    "critical": "매우 높음",
    "default channel": "기본 채널",
    "discord": "디스코드",
    "draft_coverage": "초안 작성 비율",
    "email": "이메일",
    "error": "오류",
    "evidence": "근거",
    "factuality": "사실성",
    "failed": "실패",
    "fallback_chat_link": "대체 링크 전송",
    "final_response": "최종 응답 완료 비율",
    "hallucination": "환각 위험",
    "high": "높음",
    "high_risk": "고위험",
    "human_review": "사람 검토 필요",
    "in_app": "인앱 문의",
    "info": "안내",
    "ivr": "전화 문의",
    "line": "추이",
    "low": "낮음",
    "low_factuality": "사실성 낮음",
    "manual": "수동 처리",
    "negative": "부정적",
    "negative_sentiment": "부정 반응",
    "needs_human_review": "사람 검토 필요",
    "neutral": "보통",
    "off": "꺼짐",
    "on": "켜짐",
    "open": "진행 중",
    "payment": "결제",
    "pending": "처리 대기",
    "policy_violation": "정책 위반",
    "positive": "긍정적",
    "processing": "처리 중",
    "publish": "전송",
    "quality_review": "품질 재검토",
    "rag_reply": "AI 문서 기반 응답",
    "refund": "환불",
    "response_rate": "응답 완료 비율",
    "retry_detected": "재시도 발생",
    "review": "검토",
    "safe": "문제 없음",
    "slack": "슬랙",
    "sms": "문자",
    "stop": "종료",
    "success": "성공",
    "system": "시스템",
    "ticket": "문의",
    "toxicity": "독성 위험",
    "unknown": "확인 필요",
    "urgent_alert": "즉시 알림",
    "urgent_unanswered": "긴급 미응답",
    "very_negative": "매우 부정적",
    "very_positive": "매우 긍정적",
    "voice": "음성 문의",
    "warning": "주의",
    "web": "웹 문의",
}

SECTION_LABELS: dict[str, str] = {
    "admin_event_logs": "운영 처리 이력",
    "failed_queries": "조회 실패 기록",
    "gacha_logs": "가챠 이용 기록",
    "item_delivery_logs": "아이템 지급 기록",
    "payments": "결제 기록",
    "refunds": "환불 기록",
}

TRANSLATABLE_KEYS = {
    "severity",
    "status",
    "risk_level",
    "pattern_risk_level",
    "sentiment",
    "routing_target",
    "source_type",
    "channel",
    "delivery_mode",
    "responder_type",
    "safety_action",
    "error_category",
    "kind",
    "label",
    "queue_reason",
    "coaching_reason",
    "escalation_reason",
}


def translate_label(label: str) -> str:
    return COLUMN_LABELS.get(label, label)


def translate_value(value: Any, *, key: str | None = None) -> Any:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if key == "column" and isinstance(value, str):
        return translate_label(value)
    if key in TRANSLATABLE_KEYS and isinstance(value, str):
        parts = [part.strip().lower() for part in value.split(",")]
        translated = [VALUE_LABELS.get(part, part if part else "-") for part in parts]
        return ", ".join(translated)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALUE_LABELS:
            return VALUE_LABELS[normalized]
    return value


def localized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {translate_label(key): translate_value(value, key=key) for key, value in row.items()}
        for row in rows
    ]
