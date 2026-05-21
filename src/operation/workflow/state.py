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
    """운영 워크플로우 상태 모델들이 공유하는 기본 설정입니다.

    LangGraph 노드 간 전달되는 payload와 DB/LLM에서 추가된 필드를 유연하게 연결합니다.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Ticket(OperationModel):
    """워크플로우 시작 시 로드되는 고객 문의 티켓 모델입니다.

    `qa_ticket`를 중심으로 `community_users`, `game_accounts`에서 온 메타데이터와 연결됩니다.
    """

    ticket_id: str | None = None
    user_id: str | None = None
    title: str | None = None
    body: str | None = None
    channel: str | None = None
    responder_type: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceDocument(OperationModel):
    """RAG 검색으로 가져온 근거 문서 모델입니다.

    `documents_chunks`, `documents` 조회 결과를 답변 생성과 `evidence_docs` 저장에 연결합니다.
    """

    doc_id: str | None = None
    source: str | None = None
    title: str | None = None
    content: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(OperationModel):
    """목표 route를 결정하기 전 생성되는 티켓 분석 결과입니다.

    `ticket_analysis` 테이블 저장과 RAG 답변/긴급 알림 분기 판단에 연결됩니다.
    """

    query_route: QueryRoute | None = None
    target_route: TargetRoute | None = None
    risk_level: RiskLevel | None = None
    risk_reason: str | None = None
    summary: str | None = None
    required_actions: list[str] = Field(default_factory=list)


class SafetyResult(OperationModel):
    """답변 초안의 안전성 및 근거 일치 여부를 담는 검수 결과입니다.

    `safety_results` 테이블과 승인/사람 검수/긴급 알림 route 선택에 연결됩니다.
    """

    approved: bool | None = None
    evidence_matched: bool | None = None
    hallucination_detected: bool | None = None
    policy_violation_detected: bool | None = None
    unsafe_expression_detected: bool | None = None
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResult(OperationModel):
    """운영자 검수 결정과 수정 답변을 담는 모델입니다.

    승인, 반려, 편집 흐름을 `publish_final_answer_node`, `retry_routing_node`, `edit_answer_node`에 연결합니다.
    """

    decision: HumanDecision | None = None
    reason: str | None = None
    edited_answer: str | None = None
    reviewer_id: str | None = None


class OperationState(OperationModel):
    """모든 운영 LangGraph 노드가 공유하는 전체 상태 모델입니다.

    `qa_ticket` 로드부터 `final_response` 저장 또는 `notification_logs` 알림까지의 값을 연결합니다.
    """

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
