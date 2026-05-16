from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from config import settings
from data.seed_payload import SEED_APPROVAL_INPUT_PAYLOAD, clone_payload
from operation.approvalagent.prompts import (
    APPROVAL_DECISION_PROMPT,
    EVIDENCE_ALIGNMENT_PROMPT,
    SAFETY_SCORING_PROMPT,
)


# 이 모듈의 입력/출력 계약은 docs/ddl.md, docs/operation_dashboard.md를 기준으로 유지한다.
APPROVAL_REFERENCE_DOCS = ("docs/ddl.md", "docs/operation_dashboard.md")


# 증거 정합성 점검 단계에서 반환되는 구조화 결과
class EvidenceAlignmentResult(BaseModel):
    supported_claims: list[str]
    unsupported_claims: list[str]
    risk_notes: list[str]
    needs_human_review: bool


# 안전성 점수 산출 단계에서 반환되는 구조화 결과
class SafetyScoreResult(BaseModel):
    safety_id: int
    draft_id: int
    hallucination_score: float
    toxicity_score: float
    policy_violation_score: float
    factuality_score: float
    checked_at: str


# 최종 승인 판단 결과를 담는 구조화 스키마
class ApprovalDecisionResult(BaseModel):
    approval_result: Literal["approved", "human_review", "urgent_alert"]
    review_reason: str
    recommended_action: str
    priority: Literal["normal", "high", "urgent"]


# 사람 검토가 필요할 때 생성하는 요청 payload 스키마
class HumanReviewRequestResult(BaseModel):
    ticket_id: int
    draft_id: int
    review_reason: str
    recommended_action: str
    priority: Literal["normal", "high", "urgent"]
    requested_at: str


# 운영 시스템에 저장할 최종 결과 payload 스키마
class FinalOutcomeResult(BaseModel):
    ticket_id: int
    status: str
    approval_result: Literal["approved", "human_review", "urgent_alert"]
    operator_action: str


# 승인 체인 전체를 통과하는 payload 스키마
class ApprovalPayload(BaseModel):
    qa_ticket: Any
    account_context: Any
    operation_logs: Any
    ticket_analysis: Any
    answer_draft: Any
    evidence_docs: Any
    evidence_alignment: dict[str, Any] | None = None
    safety_results: list[dict[str, Any]] | None = None
    approval_decision: dict[str, Any] | None = None
    approval_result: Literal["approved", "human_review", "urgent_alert"] | None = None
    human_review_request: dict[str, Any] | None = None
    human_review_resolution: dict[str, Any] | None = None
    final_outcome: dict[str, Any] | None = None


def _model():
    # 구조화 출력 호출마다 사용할 채팅 모델을 생성한다.
    return init_chat_model(settings.openai_model)


def _payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    # 입력 payload를 스키마에 맞게 정규화하고, 없으면 seed 데이터를 기본값으로 사용한다.
    return ApprovalPayload.model_validate(clone_payload(payload or SEED_APPROVAL_INPUT_PAYLOAD)).model_dump(
        exclude_none=True
    )


def _invoke(schema: type[BaseModel], prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    # 현재 payload를 LLM에 전달하고, 지정한 스키마 형태의 응답만 받도록 강제한다.
    return _model().with_structured_output(schema).invoke(
        [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}]
    ).model_dump()


def _merge(payload: dict[str, Any], **updates: Any) -> dict[str, Any]:
    # 원본 payload 형태를 유지한 채 단계별 결과만 덧붙인다.
    merged = clone_payload(payload)
    merged.update(updates)
    return merged


def _first(value: Any) -> dict[str, Any]:
    # seed 또는 런타임 데이터가 단일 객체나 단일 원소 리스트여도 모두 처리한다.
    return value[0] if isinstance(value, list) else value


def _decision(payload: dict[str, Any]) -> ApprovalDecisionResult:
    # approval_decision dict를 타입이 있는 모델로 복원해 안전하게 접근한다.
    return ApprovalDecisionResult.model_validate(payload["approval_decision"])


def load_approval_payload(payload: dict[str, Any] | None = None) -> dict:
    return _payload(payload)


def check_evidence_alignment(payload: dict[str, Any] | None = None) -> dict:
    # 답변 초안이 증거 문서와 얼마나 일치하는지 분석한 결과를 payload에 추가한다.
    base = _payload(payload)
    return _merge(base, evidence_alignment=_invoke(EvidenceAlignmentResult, EVIDENCE_ALIGNMENT_PROMPT, base))


def score_safety_result(payload: dict[str, Any] | None = None) -> dict:
    # 환각, 독성, 정책 위반, 사실성 점수를 포함한 안전성 평가 결과를 추가한다.
    base = _payload(payload)
    return _merge(base, safety_results=[_invoke(SafetyScoreResult, SAFETY_SCORING_PROMPT, base)])


def decide_approval_result(payload: dict[str, Any] | None = None) -> dict:
    # 누적된 분석 결과를 바탕으로 최종 승인 상태를 판정한다.
    base = _payload(payload)
    result = _invoke(ApprovalDecisionResult, APPROVAL_DECISION_PROMPT, base)
    return _merge(base, approval_decision=result, approval_result=result["approval_result"])


def build_human_review_request(payload: dict[str, Any]) -> dict:
    # 승인된 건은 그대로 두고, 그 외의 경우에만 사람 검토 요청 payload를 만든다.
    base = _payload(payload)
    decision = _decision(base)
    if decision.approval_result == "approved":
        return base
    draft = _first(base["answer_draft"])
    ticket = _first(base["qa_ticket"])
    return _merge(
        base,
        human_review_request=HumanReviewRequestResult(
            ticket_id=ticket["ticket_id"],
            draft_id=draft["draft_id"],
            review_reason=decision.review_reason,
            recommended_action=decision.recommended_action,
            priority=decision.priority,
            requested_at=datetime.now(timezone.utc).isoformat(),
        ).model_dump(),
    )


def build_final_outcome(payload: dict[str, Any]) -> dict:
    # 후속 운영 시스템이 저장할 수 있는 최종 결과 레코드를 생성한다.
    base = _payload(payload)
    decision = _decision(base)
    ticket = _first(base["qa_ticket"])
    resolution = base.get("human_review_resolution") or {}
    return _merge(
        base,
        final_outcome=FinalOutcomeResult(
            ticket_id=ticket["ticket_id"],
            status="closed",
            approval_result=decision.approval_result,
            operator_action=resolution.get("operator_action", decision.recommended_action),
        ).model_dump(),
    )


def mark_answer_draft_approved(
    payload: dict[str, Any],
    operator_action: str = "approve_final_answer",
    review_reason: str = "운영자가 답변 초안을 최종 승인함",
) -> dict:
    # 운영자가 answer_draft를 확인한 뒤 최종 승인한 상태를 승인 payload에 반영한다.
    base = _payload(payload)
    decision = ApprovalDecisionResult(
        approval_result="approved",
        review_reason=review_reason,
        recommended_action=operator_action,
        priority="normal",
    ).model_dump()
    return _merge(
        base,
        approval_decision=decision,
        approval_result="approved",
        human_review_request=None,
    )


def apply_human_review_resolution(
    payload: dict[str, Any],
    operator_action: str,
    review_note: str,
    edited_draft_text: str | None = None,
) -> dict:
    # Human 단계의 실제 처리 결과를 기록하고 FINAL 단계에 전달한다.
    base = _payload(payload)
    merged = clone_payload(base)

    if edited_draft_text:
        draft = _first(merged["answer_draft"])
        draft["draft_text"] = edited_draft_text

    merged["human_review_resolution"] = {
        "operator_action": operator_action,
        "review_note": review_note,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    return merged


def run_approval_gate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    # RESULT 노드에서 분기해 approved는 FINAL로, 나머지는 HUMAN 요청으로 보낸다.
    state = approval_core_chain.invoke(payload or {})
    if state["approval_result"] == "approved":
        return build_final_outcome(state)
    return build_human_review_request(state)


# 각 함수를 LangChain Runnable로 감싸 파이프라인으로 조합한다.
load_chain = RunnableLambda(load_approval_payload)
alignment_chain = RunnableLambda(check_evidence_alignment)
safety_chain = RunnableLambda(score_safety_result)
decision_chain = RunnableLambda(decide_approval_result)
review_request_chain = RunnableLambda(build_human_review_request)
final_outcome_chain = RunnableLambda(build_final_outcome)

# 핵심 승인 분석 및 판단 경로
approval_core_chain = load_chain | alignment_chain | safety_chain | decision_chain
# 판단 결과에 따라 사람 검토 요청 생성까지 포함한 경로
approval_review_chain = approval_core_chain | review_request_chain
# 최종 결과 생성까지 포함한 전체 승인 체인
approval_chain = RunnableLambda(run_approval_gate)
