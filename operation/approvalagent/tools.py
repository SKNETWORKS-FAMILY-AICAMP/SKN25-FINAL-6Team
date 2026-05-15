from __future__ import annotations

import json
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import settings
from data.seed_payload import SEED_APPROVAL_INPUT_PAYLOAD, clone_payload


class EvidenceAlignmentResult(BaseModel):
    supported_claims: list[str] = Field(description="Draft claims supported by evidence.")
    unsupported_claims: list[str] = Field(description="Draft claims not clearly supported by evidence.")
    risk_notes: list[str] = Field(description="Short notes about approval risks.")
    needs_human_review: bool = Field(description="Whether a human should review the draft.")


class SafetyScoreResult(BaseModel):
    safety_id: int = Field(description="Safety result identifier.")
    draft_id: int = Field(description="Draft identifier.")
    hallucination_score: float = Field(description="0 to 1 score for hallucination risk.")
    toxicity_score: float = Field(description="0 to 1 score for toxicity risk.")
    policy_violation_score: float = Field(description="0 to 1 score for policy violation risk.")
    factuality_score: float = Field(description="0 to 1 score for factual correctness.")
    checked_at: str = Field(description="ISO timestamp when the check was completed.")


class ApprovalDecisionResult(BaseModel):
    approval_result: Literal["approved", "human_review", "urgent_alert"] = Field(
        description="Final approval routing decision."
    )
    review_reason: str = Field(description="Short reason for the decision.")
    recommended_action: str = Field(description="Recommended operator action.")
    priority: Literal["normal", "high", "urgent"] = Field(description="Review priority.")


class HumanReviewRequestResult(BaseModel):
    ticket_id: int = Field(description="Ticket identifier.")
    draft_id: int = Field(description="Draft identifier.")
    review_reason: str = Field(description="Why human review is needed.")
    recommended_action: str = Field(description="Recommended next action.")
    priority: Literal["normal", "high", "urgent"] = Field(description="Review priority.")
    requested_at: str = Field(description="ISO timestamp when review was requested.")


class FinalOutcomeResult(BaseModel):
    ticket_id: int = Field(description="Ticket identifier.")
    status: str = Field(description="Ticket status after approval stage.")
    approval_result: Literal["approved", "human_review", "urgent_alert"] = Field(
        description="Final approval result."
    )
    operator_action: str = Field(description="Operator action to take.")


class ApprovalGateResult(BaseModel):
    safety_results: list[SafetyScoreResult] = Field(description="Safety scoring results.")
    approval_result: Literal["approved", "human_review", "urgent_alert"] = Field(
        description="Final approval routing result."
    )
    human_review_request: HumanReviewRequestResult | None = Field(
        default=None,
        description="Present when human review is required.",
    )
    final_outcome: FinalOutcomeResult = Field(description="Final approval-stage outcome.")


def _default_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is not None:
        return clone_payload(payload)
    return clone_payload(SEED_APPROVAL_INPUT_PAYLOAD)


def _get_model():
    return init_chat_model(settings.openai_model)


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _invoke_structured(schema: type[BaseModel], system_prompt: str, payload: dict[str, Any]) -> BaseModel:
    model = _get_model().with_structured_output(schema)
    return model.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _serialize_payload(payload)},
        ]
    )


@tool
def load_approval_payload(payload: dict[str, Any] | None = None) -> dict:
    """Load the approval payload or return the seed approval payload."""
    return _default_payload(payload)


@tool
def check_evidence_alignment(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to judge whether the answer draft is supported by the evidence docs."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        EvidenceAlignmentResult,
        (
            "You are an approval gate reviewer. "
            "Compare answer_draft with evidence_docs. "
            "List supported claims, unsupported claims, concise risk notes, and whether human review is needed. "
            "Do not invent claims outside the payload."
        ),
        resolved_payload,
    )
    return result.model_dump()


@tool
def score_safety_result(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to score the draft for hallucination, toxicity, policy violation, and factuality."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        SafetyScoreResult,
        (
            "You are an approval gate reviewer. "
            "Score the answer draft against the payload. "
            "Return hallucination_score, toxicity_score, policy_violation_score, and factuality_score between 0 and 1. "
            "Set safety_id and draft_id consistently with the payload. "
            "Set checked_at to an ISO timestamp string."
        ),
        resolved_payload,
    )
    return result.model_dump()


@tool
def decide_approval_result(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to decide whether the draft is approved, needs human review, or needs urgent alerting."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        ApprovalDecisionResult,
        (
            "You are an approval gate reviewer. "
            "Decide one of approved, human_review, or urgent_alert from the payload. "
            "Use the draft, evidence, routing_target, and operation logs. "
            "If a paid-item delivery failure or high-risk payment issue is present, be conservative. "
            "Return a short review_reason, recommended_action, and priority."
        ),
        resolved_payload,
    )
    return result.model_dump()


@tool
def build_human_review_request(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to build the human review request payload."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        HumanReviewRequestResult,
        (
            "You are an approval gate reviewer. "
            "Build a human review request from the payload. "
            "Assume the case requires human review or urgent alerting. "
            "Return ticket_id, draft_id, review_reason, recommended_action, priority, and requested_at."
        ),
        resolved_payload,
    )
    return result.model_dump()


@tool
def build_final_outcome(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to build the final approval-stage outcome payload."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        FinalOutcomeResult,
        (
            "You are an approval gate reviewer. "
            "Build the final approval-stage outcome from the payload. "
            "Return ticket_id, status, approval_result, and operator_action. "
            "Keep the result consistent with the approval decision implied by the payload."
        ),
        resolved_payload,
    )
    return result.model_dump()


@tool
def run_approval_gate(payload: dict[str, Any] | None = None) -> dict:
    """Use the LLM to run the approval gate end-to-end and return a fully structured result."""
    resolved_payload = _default_payload(payload)
    result = _invoke_structured(
        ApprovalGateResult,
        (
            "You are the approval gate for a game CS workflow. "
            "Review the payload and return the full approval-stage result. "
            "You must produce safety_results, approval_result, and final_outcome. "
            "If approval_result is human_review or urgent_alert, also produce human_review_request. "
            "Be conservative for payment success plus item delivery failure cases."
        ),
        resolved_payload,
    )
    return result.model_dump()


tools = [
    load_approval_payload,
    check_evidence_alignment,
    score_safety_result,
    decide_approval_result,
    build_human_review_request,
    build_final_outcome,
    run_approval_gate,
]
