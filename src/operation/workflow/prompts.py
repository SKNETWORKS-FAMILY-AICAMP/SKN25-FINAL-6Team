"""Prompt builders for the operation workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .state import EvidenceDocument, OperationState, QueryRoute, RiskLevel, TargetRoute


class PromptModel(BaseModel):
    """LLM 구조화 응답 모델이 공유하는 기본 설정입니다.

    프롬프트 출력과 각 workflow 노드의 상태 업데이트 계약을 엄격하게 연결합니다.
    """

    model_config = ConfigDict(extra="forbid")


class QueryRoutingResponse(PromptModel):
    """문의 유형 분류 LLM 응답 모델입니다.

    `query_router` 노드와 route별 context 노드 선택에 연결됩니다.
    """

    query_route: QueryRoute
    route_reason: str


class TicketAnalysisResponse(PromptModel):
    """티켓 분석 LLM 응답 모델입니다.

    `analyze_ticket` 노드와 `ticket_analysis` 저장, 목표 route 분기에 연결됩니다.
    """

    query_route: QueryRoute
    target_route: TargetRoute
    risk_level: RiskLevel
    risk_reason: str
    summary: str
    required_actions: list[str] = Field(default_factory=list)


class AnswerDraftResponse(PromptModel):
    """근거 기반 고객 답변 초안 LLM 응답 모델입니다.

    `generate_answer_node`, `answer_draft`, `evidence_docs` 저장 흐름과 연결됩니다.
    """

    answer_draft: str
    evidence_doc_ids: list[str] = Field(default_factory=list)


class UrgentDraftResponse(PromptModel):
    """긴급 운영자 알림 초안 LLM 응답 모델입니다.

    `urgent_draft_node`와 `notification_logs`에 남길 운영 알림 메시지에 연결됩니다.
    """

    urgent_draft: str


class SafetyReviewResponse(PromptModel):
    """승인 게이트의 안전성 검수 LLM 응답 모델입니다.

    `approval_gate_node`, `safety_results`, 승인/검수/긴급 알림 분기에 연결됩니다.
    """

    approved: bool
    evidence_matched: bool
    hallucination_detected: bool
    policy_violation_detected: bool
    unsafe_expression_detected: bool
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResponse(PromptModel):
    """운영자 검수 결정을 보조하는 LLM 응답 모델입니다.

    `human_review_node`와 승인, 반려, 편집 후속 노드 선택에 연결됩니다.
    """

    decision: str
    reason: str
    edited_answer: str | None = None


SYSTEM_PROMPT = """You are an operation workflow assistant for a game customer-support system.
Use only the ticket, database context, and retrieved evidence provided in the prompt.
Return only JSON that matches the requested schema.
Do not invent user data, payment state, refund state, item delivery state, policy text, or incident status."""


QUERY_ROUTER_PROMPT = """Classify the ticket into one query route.

Allowed query_route values:
- payment: payment, purchase, transaction, billing, currency, product payment status
- refund: refund request, refund failure, refund policy application
- item_delivery: purchased or rewarded item delivery, missing item, delayed item
- gacha: gacha pull, banner, rarity, pity count, probability issue
- policy: game policy, notice, official guide, terms, normal help request
- abuse: abusive content, harassment, exploit, account abuse, policy-risk user behavior
- outage: service failure, incident, outage, access failure, widespread disruption

Ticket and context:
{state_json}"""


ANALYSIS_PROMPT = """Analyze the ticket using the selected route and database context.

Set target_route to urgent_alert only when the case needs immediate operator attention, such as critical risk, outage, abuse escalation, policy violation, payment/refund risk, or missing authoritative evidence for a high-impact decision.
Otherwise set target_route to rag_reply.

Ticket and context:
{state_json}"""


ANSWER_PROMPT = """Write a Korean customer-support answer draft grounded in retrieved evidence and database context.

Rules:
- Answer directly and politely.
- Use database context only when it belongs to this ticket/user/account.
- Cite evidence by returning evidence_doc_ids.
- If evidence is insufficient, say what should be checked by an operator.

Ticket, context, analysis, and evidence:
{state_json}"""


URGENT_PROMPT = """Write a concise Korean urgent alert draft for an operator.

Include ticket id, route, risk level, risk reason, relevant database context, and required actions.

Workflow state:
{state_json}"""


SAFETY_PROMPT = """Review the answer draft before final publication.

Check:
- Whether the draft is grounded in retrieved evidence and database context.
- Whether hallucination is present.
- Whether policy violation is present.
- Whether unsafe, defamatory, threatening, discriminatory, or overly definitive language is present.

Workflow state:
{state_json}"""


HUMAN_REVIEW_PROMPT = """Prepare an operator review recommendation for the answer draft.

decision must be one of approved, reject, edit.
Use edit when the answer can be fixed safely with a small correction.
Use reject when the workflow should reroute and regenerate.

Workflow state:
{state_json}"""


def render_state(state: OperationState) -> str:
    """워크플로우 상태를 LLM 프롬프트용 JSON 문자열로 직렬화합니다.

    모든 LLM 노드가 같은 `OperationState` 정보를 참조하도록 프롬프트와 상태를 연결합니다.
    """

    return state.model_dump_json(exclude_none=True, ensure_ascii=False, indent=2)


def render_documents(documents: list[EvidenceDocument]) -> str:
    """검색된 근거 문서 목록을 프롬프트용 문자열로 직렬화합니다.

    `EvidenceDocument` 목록을 답변 생성 프롬프트와 근거 검수 기능에 연결합니다.
    """

    return "\n".join(document.model_dump_json(exclude_none=True, ensure_ascii=False) for document in documents)
