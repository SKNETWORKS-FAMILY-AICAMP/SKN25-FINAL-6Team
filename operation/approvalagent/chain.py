from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from config import settings
from data.seed_payload import SEED_APPROVAL_INPUT_PAYLOAD, clone_payload
from operation.approvalagent.prompts import (
    APPROVAL_DECISION_PROMPT,
    EVIDENCE_ALIGNMENT_PROMPT,
    SAFETY_SCORING_PROMPT,
)


class EvidenceAlignmentResult(BaseModel):
    supported_claims: list[str]
    unsupported_claims: list[str]
    risk_notes: list[str]
    needs_human_review: bool


class SafetyScoreResult(BaseModel):
    safety_id: int
    draft_id: int
    hallucination_score: float
    toxicity_score: float
    policy_violation_score: float
    factuality_score: float
    checked_at: str


class ApprovalDecisionResult(BaseModel):
    approval_result: Literal["approved", "human_review", "urgent_alert"]
    review_reason: str
    recommended_action: str
    priority: Literal["normal", "high", "urgent"]


class HumanReviewRequestResult(BaseModel):
    ticket_id: int
    draft_id: int
    review_reason: str
    recommended_action: str
    priority: Literal["normal", "high", "urgent"]
    requested_at: str


class FinalOutcomeResult(BaseModel):
    ticket_id: int
    status: str
    approval_result: Literal["approved", "human_review", "urgent_alert"]
    operator_action: str


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
    final_outcome: dict[str, Any] | None = None


def _model():
    return init_chat_model(settings.openai_model)


def _payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return ApprovalPayload.model_validate(clone_payload(payload or SEED_APPROVAL_INPUT_PAYLOAD)).model_dump(
        exclude_none=True
    )


def _invoke(schema: type[BaseModel], prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _model().with_structured_output(schema).invoke(
        [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}]
    ).model_dump()


def _merge(payload: dict[str, Any], **updates: Any) -> dict[str, Any]:
    merged = clone_payload(payload)
    merged.update(updates)
    return merged


def _first(value: Any) -> dict[str, Any]:
    return value[0] if isinstance(value, list) else value


def _decision(payload: dict[str, Any]) -> ApprovalDecisionResult:
    return ApprovalDecisionResult.model_validate(payload["approval_decision"])


def load_approval_payload(payload: dict[str, Any] | None = None) -> dict:
    return _payload(payload)


def check_evidence_alignment(payload: dict[str, Any] | None = None) -> dict:
    base = _payload(payload)
    return _merge(base, evidence_alignment=_invoke(EvidenceAlignmentResult, EVIDENCE_ALIGNMENT_PROMPT, base))


def score_safety_result(payload: dict[str, Any] | None = None) -> dict:
    base = _payload(payload)
    return _merge(base, safety_results=[_invoke(SafetyScoreResult, SAFETY_SCORING_PROMPT, base)])


def decide_approval_result(payload: dict[str, Any] | None = None) -> dict:
    base = _payload(payload)
    result = _invoke(ApprovalDecisionResult, APPROVAL_DECISION_PROMPT, base)
    return _merge(base, approval_decision=result, approval_result=result["approval_result"])


def build_human_review_request(payload: dict[str, Any]) -> dict:
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
    base = _payload(payload)
    decision = _decision(base)
    ticket = _first(base["qa_ticket"])
    return _merge(
        base,
        final_outcome=FinalOutcomeResult(
            ticket_id=ticket["ticket_id"],
            status="closed",
            approval_result=decision.approval_result,
            operator_action=decision.recommended_action,
        ).model_dump(),
    )


load_chain = RunnableLambda(load_approval_payload)
alignment_chain = RunnableLambda(check_evidence_alignment)
safety_chain = RunnableLambda(score_safety_result)
decision_chain = RunnableLambda(decide_approval_result)
review_request_chain = RunnableLambda(build_human_review_request)
final_outcome_chain = RunnableLambda(build_final_outcome)

approval_core_chain = load_chain | alignment_chain | safety_chain | decision_chain
approval_review_chain = approval_core_chain | review_request_chain
approval_chain = approval_review_chain | final_outcome_chain
