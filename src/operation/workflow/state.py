"""Pydantic state schema for the operation ticket-processing workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


QueryRoute = Literal[
    "payment",
    "refund",
    "item_delivery",
    "gacha",
    "policy",
    "abuse",
    "outage",
]
TargetRoute = Literal["rag_reply", "urgent_alert"]
ApprovalRoute = Literal["approved", "human_review", "urgent_alert"]
HumanDecision = Literal["approved", "reject", "edit"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class OperationModel(BaseModel):
    """Base model config shared by operation workflow state objects."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Ticket(OperationModel):
    """Inbound customer ticket loaded at the start of the workflow."""

    ticket_id: str | None = None
    user_id: str | None = None
    title: str | None = None
    body: str | None = None
    channel: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceDocument(OperationModel):
    """Document retrieved from policy, notice, guide, or incident sources."""

    doc_id: str | None = None
    source: str | None = None
    title: str | None = None
    content: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(OperationModel):
    """Structured analysis produced before target routing."""

    query_route: QueryRoute | None = None
    target_route: TargetRoute | None = None
    risk_level: RiskLevel | None = None
    risk_reason: str | None = None
    summary: str | None = None
    required_actions: list[str] = Field(default_factory=list)


class SafetyResult(OperationModel):
    """Safety and grounding result used by the approval router."""

    approved: bool | None = None
    evidence_matched: bool | None = None
    hallucination_detected: bool | None = None
    policy_violation_detected: bool | None = None
    unsafe_expression_detected: bool | None = None
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResult(OperationModel):
    """Operator review decision and optional edit payload."""

    decision: HumanDecision | None = None
    reason: str | None = None
    edited_answer: str | None = None
    reviewer_id: str | None = None


class OperationState(OperationModel):
    """Shared state passed through all operation LangGraph nodes."""

    ticket_id: str | None = None
    ticket: Ticket = Field(default_factory=Ticket)
    query_text: str | None = None
    query_route: QueryRoute | None = None
    query_route_reason: str | None = None
    target_route: TargetRoute | None = None
    approval_route: ApprovalRoute | None = None
    human_decision: HumanDecision | None = None

    context: dict[str, Any] = Field(default_factory=dict)
    context_nodes: list[str] = Field(default_factory=list)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    retrieved_docs: list[EvidenceDocument] = Field(default_factory=list)
    answer_draft: str | None = None
    urgent_draft: str | None = None
    evidence_doc_ids: list[str] = Field(default_factory=list)
    safety_result: SafetyResult = Field(default_factory=SafetyResult)
    human_review: HumanReviewResult = Field(default_factory=HumanReviewResult)
    edited_answer: str | None = None
    final_answer: str | None = None

    analysis_id: int | None = None
    draft_id: int | None = None
    safety_id: int | None = None
    response_id: int | None = None
    retry_count: int | None = None
    max_retries: int | None = None
    status: str | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
