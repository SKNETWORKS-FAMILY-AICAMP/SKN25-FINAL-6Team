"""Prompt models and templates for the 4-agent operation workflow."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .state import ApprovalRoute, EvidenceDocument, HumanDecision, OperationState, QueryRoute, RiskLevel, TargetRoute


class PromptModel(BaseModel):
    """Strict response model for structured LLM calls."""

    model_config = ConfigDict(extra="forbid")


class IntakeAgentResponse(PromptModel):
    """Structured response for the intake agent."""

    query_route: QueryRoute
    route_reason: str
    target_route: TargetRoute
    risk_level: RiskLevel
    risk_reason: str
    summary: str
    required_actions: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    required_context_types: list[str] = Field(default_factory=list)


class DraftingAgentResponse(PromptModel):
    """Structured response for the drafting agent."""

    customer_answer: str | None = None
    operator_handoff_answer: str | None = None
    urgent_alert_message: str | None = None
    evidence_doc_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None


class ReviewAgentResponse(PromptModel):
    """Structured response for the review agent."""

    approval_route: ApprovalRoute
    approved: bool
    evidence_matched: bool
    hallucination_detected: bool
    policy_violation_detected: bool
    unsafe_expression_detected: bool
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResponse(PromptModel):
    """Structured response for the human review step."""

    decision: HumanDecision
    reason: str
    edited_answer: str | None = None


SYSTEM_PROMPT = """You are an operation workflow assistant for a game customer-support system.
Use only the ticket, database context, and retrieved evidence provided in the prompt.
Return only JSON that matches the requested schema.
Do not invent user data, payment state, refund state, item delivery state, policy text, or incident status."""


INTAKE_SYSTEM_PROMPT = """You are the intake agent for a game customer-support workflow.
Classify the inquiry, assess risk, choose rag_reply or urgent_alert, and decide whether human review is required.
Use only the workflow state provided.
Return only JSON that matches the requested schema."""


INTAKE_USER_PROMPT = """Analyze the workflow state and return:
- query_route
- route_reason
- target_route
- risk_level
- risk_reason
- summary
- required_actions
- review_required
- review_reason
- required_context_types

Workflow state:
{state_json}"""


DRAFTING_SYSTEM_PROMPT = """You are the drafting agent for a game customer-support workflow.
Use only retrieved evidence and database context.
Return customer-facing text for normal cases, operator handoff text for review cases, and urgent alert text for urgent cases.
Do not invent facts.
Return only JSON that matches the requested schema."""


DRAFTING_USER_PROMPT = """Draft the response for this workflow state.

Rules:
- If target_route is rag_reply, fill customer_answer.
- If target_route is urgent_alert, fill urgent_alert_message.
- If review is needed, set review_required=true and explain why.
- Return evidence_doc_ids that support the draft.

Workflow state:
{state_json}"""


REVIEW_SYSTEM_PROMPT = """You are the review agent for a game customer-support workflow.
Check factual grounding, hallucination risk, policy violations, and unsafe language.
Decide whether the workflow can publish, needs human review, or must raise urgent alert.
Return only JSON that matches the requested schema."""


REVIEW_USER_PROMPT = """Review this workflow state and return:
- approval_route
- approved
- evidence_matched
- hallucination_detected
- policy_violation_detected
- unsafe_expression_detected
- reasons

Workflow state:
{state_json}"""


HUMAN_REVIEW_SYSTEM_PROMPT = """You are assisting a human reviewer in a game customer-support workflow.
The reviewer must choose one action: approve the current answer, edit it, or regenerate from intake.
Return only JSON that matches the requested schema."""


HUMAN_REVIEW_PROMPT = """Review the current workflow result and decide one action.

Rules:
- Use approved when the current answer can be sent as-is.
- Use edit when the answer only needs direct text correction. Provide edited_answer.
- Use regenerate when the answer should be regenerated from intake. Explain the reason clearly.

Workflow state:
{state_json}"""


def render_state(state: OperationState) -> str:
    """Serialize workflow state for prompt injection."""

    return json.dumps(
        state.model_dump(exclude_none=True),
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _truncate_text(value: Any, max_chars: int) -> Any:
    if not isinstance(value, str) or len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _truncate_mapping(value: Any, max_chars: int) -> Any:
    if isinstance(value, dict):
        return {key: _truncate_mapping(item, max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_mapping(item, max_chars) for item in value]
    return _truncate_text(value, max_chars)


def render_state_for_drafting(state: OperationState) -> str:
    """Serialize a compact workflow state for the drafting LLM call."""

    max_docs = int(os.environ.get("DRAFTING_MAX_EVIDENCE_DOCS", "5"))
    max_doc_chars = int(os.environ.get("DRAFTING_MAX_EVIDENCE_CHARS", "1800"))
    max_context_items = int(os.environ.get("DRAFTING_MAX_CONTEXT_ITEMS", "8"))
    max_context_chars = int(os.environ.get("DRAFTING_MAX_CONTEXT_CHARS", "1200"))

    payload = state.model_dump(exclude_none=True)
    payload["retrieved_docs"] = [
        {
            **doc.model_dump(exclude_none=True, exclude={"metadata"}),
            "content": _truncate_text(doc.content, max_doc_chars),
        }
        for doc in state.retrieved_docs[:max_docs]
    ]
    payload["context"] = {
        key: _truncate_mapping(value[:max_context_items] if isinstance(value, list) else value, max_context_chars)
        for key, value in state.context.items()
    }
    payload.pop("metadata", None)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def render_documents(documents: list[EvidenceDocument]) -> str:
    """Serialize evidence documents for debugging or prompt use."""

    return "\n".join(document.model_dump_json(exclude_none=True) for document in documents)
