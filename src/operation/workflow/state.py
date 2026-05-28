"""Pydantic state schema for the operation ticket-processing workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ─── Literal 타입 정의 ─────────────────────────────────────────────────────────
# LangGraph 라우터 함수의 반환값으로 사용한다.
# Literal로 선언하면 잘못된 route 값이 코드에서 즉시 타입 오류로 드러난다.

# query_router가 반환할 수 있는 업무 분류 7종
# payment        : 결제·구매·청구 문의
# refund         : 환불 요청 및 처리 문의
# item_delivery  : 구매 또는 보상 아이템 미지급 문의
# gacha          : 가챠 뽑기·배너·확률·pity 문의
# policy         : 정책·공지·가이드·약관 등 일반 문의
# abuse          : 어뷰징·신고·계정 정지 관련 위험 문의
# outage         : 서비스 장애·접속 불가·광범위 이슈
QueryRoute = Literal[
    "payment",
    "refund",
    "item_delivery",
    "gacha",
    "policy",
    "abuse",
    "outage",
]

# analyze_ticket 이후 목표 경로 2종
# rag_reply      : RAG 검색 기반 일반 답변 생성
# urgent_alert   : 즉시 운영자 에스컬레이션 (critical 위험, 장애, 정책 위반 등)
TargetRoute = Literal["rag_reply", "urgent_alert"]

# approval_gate_node가 설정하는 승인 경로 3종
# approved       : LLM 안전성 검수 통과 → 최종 발행
# human_review   : 검수 미통과지만 수정 가능 → 운영자 검수
# urgent_alert   : 정책 위반 또는 critical 위험 → 즉시 긴급 알림
ApprovalRoute = Literal["approved", "human_review", "urgent_alert"]

# human_review_node가 설정하는 운영자 결정 3종
# approved       : 초안 그대로 최종 발행
# reject         : 초안 폐기 후 재라우팅 (retry_routing_node)
# edit           : 수정 답변을 바로 발행 (edit_answer_node)
HumanDecision = Literal["approved", "reject", "edit"]

# 위험도 4단계 — ticket_analysis.risk_level 컬럼과 매핑
# critical일 때 approval_gate_node는 urgent_alert를 강제한다
RiskLevel = Literal["low", "medium", "high", "critical"]


class OperationModel(BaseModel):
    """운영 워크플로우 상태 모델들이 공유하는 기본 설정입니다.

    LangGraph 노드 간 전달되는 payload와 DB/LLM에서 추가된 필드를 유연하게 연결합니다.
    """

    # extra="allow": LangGraph가 state에 추가 키를 주입하거나 노드가 선언되지 않은 필드를
    # 반환해도 ValidationError 없이 수용한다. notification_id 등 extra 필드가 여기서 동작한다.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Ticket(OperationModel):
    """워크플로우 시작 시 로드되는 고객 문의 티켓 모델입니다.

    `qa_ticket`를 중심으로 `community_users`, `game_accounts`에서 온 메타데이터와 연결됩니다.
    """

    # qa_ticket.ticket_id (문자열로 정규화해 FK 연결에 사용)
    ticket_id: str | None = None
    # qa_ticket.user_id → community_users.user_id
    user_id: str | None = None
    # qa_ticket.title
    title: str | None = None
    # qa_ticket.raw_query (LLM 입력용 본문; 없으면 title을 대체 사용)
    body: str | None = None
    # qa_ticket.source_type (예: "community", "email")
    channel: str | None = None
    # qa_ticket.responder_type (예: "bot", "human")
    responder_type: str | None = None
    # qa_ticket.inquiry_created_at (문자열 변환 후 저장)
    created_at: str | None = None
    # load_ticket이 DB 행 전체를 여기에 담아 context 노드가 account_id 등을 꺼낼 수 있게 한다
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceDocument(OperationModel):
    """RAG 검색으로 가져온 근거 문서 모델입니다.

    `documents_chunks`, `documents` 조회 결과를 답변 생성과 `evidence_docs` 저장에 연결합니다.
    """

    # documents_chunks.chunk_id (evidence_docs.source_id 로 저장됨)
    doc_id: str | None = None
    # documents.source_type (예: "policy", "incident")
    source: str | None = None
    # documents.title
    title: str | None = None
    # documents_chunks.chunk_text (LLM 답변 생성 입력 및 evidence_docs.evidence_text)
    content: str | None = None
    # RRF 병합 후 최종 relevance score (evidence_docs.relevance_score 로 저장됨)
    score: float | None = None
    # DB 조회 행 전체 (원본 chunk_id, document_id 등 추적에 사용)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(OperationModel):
    """목표 route를 결정하기 전 생성되는 티켓 분석 결과입니다.

    `ticket_analysis` 테이블 저장과 RAG 답변/긴급 알림 분기 판단에 연결됩니다.
    """

    # LLM이 재분류한 query_route (ticket_analysis.category 로 저장됨)
    query_route: QueryRoute | None = None
    # rag_reply 또는 urgent_alert (ticket_analysis.routing_target 으로 저장됨)
    target_route: TargetRoute | None = None
    # low / medium / high / critical (ticket_analysis.risk_level 로 저장됨)
    risk_level: RiskLevel | None = None
    # risk_level 판단 근거 (ticket_analysis에 직접 저장하지 않고 LLM 디버깅에 사용)
    risk_reason: str | None = None
    # 티켓 요약문 (ticket_analysis.summary 로 저장됨)
    summary: str | None = None
    # 운영자가 취해야 할 조치 목록 (LLM 응답; DB 저장 없이 프롬프트 체인에서만 사용됨)
    required_actions: list[str] = Field(default_factory=list)


class SafetyResult(OperationModel):
    """답변 초안의 안전성 및 근거 일치 여부를 담는 검수 결과입니다.

    `safety_results` 테이블과 승인/사람 검수/긴급 알림 route 선택에 연결됩니다.
    """

    # True: 안전성 검수 통과 (approved route 조건)
    approved: bool | None = None
    # True: 초안 내용이 검색된 근거와 일치 (factuality_score=1.0 으로 저장됨)
    evidence_matched: bool | None = None
    # True: 초안에 사실 왜곡 의심 내용 포함 (hallucination_score=1.0 으로 저장됨)
    hallucination_detected: bool | None = None
    # True: 초안에 정책 위반 표현 포함 → approval_gate가 urgent_alert 강제 (policy_violation_score=1.0)
    policy_violation_detected: bool | None = None
    # True: 초안에 위험·차별·명예훼손 등 부적절한 표현 포함 (toxicity_score=1.0 으로 저장됨)
    unsafe_expression_detected: bool | None = None
    # 검수 판단 근거 목록 (safety_results.safety_reason 에 줄바꿈으로 합쳐 저장됨)
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResult(OperationModel):
    """운영자 검수 결정과 수정 답변을 담는 모델입니다.

    승인, 반려, 편집 흐름을 `publish_final_answer_node`, `retry_routing_node`, `edit_answer_node`에 연결합니다.
    """

    # approved / reject / edit 중 하나 (human_review_node LLM 응답 또는 API 직접 설정)
    decision: HumanDecision | None = None
    # 검수 결정 이유 (reject 시 retry_reason 으로 다음 라우팅에 주입됨)
    reason: str | None = None
    # edit 결정 시 운영자가 수정한 최종 답변 텍스트
    edited_answer: str | None = None
    # 검수자 식별자 (admin_event_logs.metadata.reviewer_id 로 기록됨)
    reviewer_id: str | None = None


class OperationState(OperationModel):
    """모든 운영 LangGraph 노드가 공유하는 전체 상태 모델입니다.

    `qa_ticket` 로드부터 `final_response` 저장 또는 `notification_logs` 알림까지의 값을 연결합니다.
    """

    # 워크플로우 진입점 — run_workflow API가 주입하는 티켓 ID (문자열)
    ticket_id: str | None = None
    # load_ticket 노드가 DB에서 채우는 티켓 상세 정보
    ticket: Ticket = Field(default_factory=Ticket)
    # LLM/RAG 검색에 사용할 문의 원문 (qa_ticket.raw_query; 없으면 title)
    query_text: str | None = None

    # query_router가 설정하는 업무 분류 (payment / refund / ... / outage)
    query_route: QueryRoute | None = None
    # query_router가 분류 이유를 기록하는 필드 (로그·디버깅 목적)
    query_route_reason: str | None = None
    # analyze_ticket이 설정하는 목표 route (rag_reply / urgent_alert)
    target_route: TargetRoute | None = None
    # approval_gate_node가 설정하는 승인 경로 (approved / human_review / urgent_alert)
    approval_route: ApprovalRoute | None = None
    # human_review_node가 설정하는 운영자 결정 (approved / reject / edit)
    human_decision: HumanDecision | None = None

    # context 노드들이 채우는 업무 데이터 (key: route 이름, value: DB 행 목록)
    context: dict[str, Any] = Field(default_factory=dict)
    # 실행된 context 노드 이름 목록 (로그·디버깅 목적)
    context_nodes: list[str] = Field(default_factory=list)
    # analyze_ticket 결과 (ticket_analysis 저장 및 다음 route 결정에 사용)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    # rag_retrieve_node가 반환하는 검색 근거 문서 목록
    retrieved_docs: list[EvidenceDocument] = Field(default_factory=list)
    # generate_answer_node가 생성한 고객 답변 초안 (answer_draft 테이블에 저장됨)
    answer_draft: str | None = None
    # urgent_draft_node가 생성한 운영자 알림 초안 (notification_logs에 저장됨)
    urgent_draft: str | None = None
    # generate_answer_node가 인용한 chunk_id 목록 (evidence_docs.source_id 로 저장됨)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    # approval_gate_node 안전성 검수 결과 (safety_results 테이블에 저장됨)
    safety_result: SafetyResult = Field(default_factory=SafetyResult)
    # human_review_node 운영자 결정 (결정 경로에 따라 다음 노드로 전달됨)
    human_review: HumanReviewResult = Field(default_factory=HumanReviewResult)
    # edit 결정 시 수정된 답변 (publish_final_answer_node가 최우선 사용)
    edited_answer: str | None = None
    # 최종 발행된 답변 (final_response.final_text 로 저장되고 API 응답으로 반환됨)
    final_answer: str | None = None

    # save_analysis가 RETURNING으로 받는 ticket_analysis.analysis_id
    analysis_id: int | None = None
    # save_draft_node가 RETURNING으로 받는 answer_draft.draft_id
    draft_id: int | None = None
    # save_safety_result_node가 RETURNING으로 받는 safety_results.safety_id
    safety_id: int | None = None
    # publish_final_answer_node가 RETURNING으로 받는 final_response.response_id
    response_id: int | None = None

    # retry_routing_node가 관리하는 재시도 횟수 (초기값 None → 0으로 취급)
    retry_count: int | None = None
    # 최대 재시도 횟수 (None → 기본값 3; 초과 시 urgent_alert_node로 에스컬레이션)
    max_retries: int | None = None
    # 현재 티켓 처리 상태 (qa_ticket.status 와 동기화 또는 워크플로우 내부 상태)
    status: str | None = None
    # 각 노드에서 발생한 비치명적 오류 메시지 목록 (예외를 전파하지 않고 여기에 기록)
    errors: list[str] = Field(default_factory=list)
    # 재시도 이유, 세션 등 노드 간 보조 데이터 (retry_reason 등)
    metadata: dict[str, Any] = Field(default_factory=dict)
