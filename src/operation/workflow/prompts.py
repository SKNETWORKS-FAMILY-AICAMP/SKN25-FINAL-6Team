"""Prompt builders for the operation workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .state import EvidenceDocument, HumanDecision, OperationState, QueryRoute, RiskLevel, TargetRoute


class PromptModel(BaseModel):
    """LLM 구조화 응답 모델이 공유하는 기본 설정입니다.

    프롬프트 출력과 각 workflow 노드의 상태 업데이트 계약을 엄격하게 연결합니다.
    """

    # extra="forbid": LLM이 스키마에 없는 필드를 반환하면 즉시 ValidationError를 발생시킨다.
    # OperationModel의 extra="allow"와 반대 방향 — LLM 응답을 엄격하게 검증해 hallucination 방지.
    model_config = ConfigDict(extra="forbid")


class QueryRoutingResponse(PromptModel):
    """문의 유형 분류 LLM 응답 모델입니다.

    `query_router` 노드와 route별 context 노드 선택에 연결됩니다.
    """

    # 허용값: payment / refund / item_delivery / gacha / policy / abuse / outage
    # 허용값 외 반환 시 query_router 노드가 "policy"로 fallback한다
    query_route: QueryRoute
    # 분류 이유 — state.query_route_reason 으로 저장되고 로그에 기록된다
    route_reason: str


class TicketAnalysisResponse(PromptModel):
    """티켓 분석 LLM 응답 모델입니다.

    `analyze_ticket` 노드와 `ticket_analysis` 저장, 목표 route 분기에 연결됩니다.
    """

    # 분석 단계에서 재분류된 query_route (ticket_analysis.category 로 저장됨)
    query_route: QueryRoute
    # rag_reply 또는 urgent_alert 만 허용 (ticket_analysis.routing_target 으로 저장됨)
    # critical 위험, 장애, 정책 위반은 urgent_alert로 분류해야 한다
    target_route: TargetRoute
    # low / medium / high / critical (ticket_analysis.risk_level 로 저장됨)
    # critical이면 approval_gate_node가 승인 여부와 무관하게 urgent_alert를 강제한다
    risk_level: RiskLevel
    # risk_level 판단 이유 — LLM 디버깅 및 운영자 검토용
    risk_reason: str
    # 티켓 1~3줄 요약 (ticket_analysis.summary 로 저장됨)
    summary: str
    # 운영자가 취해야 할 구체적 조치 목록 (빈 리스트 허용)
    required_actions: list[str] = Field(default_factory=list)


class AnswerDraftResponse(PromptModel):
    """근거 기반 고객 답변 초안 LLM 응답 모델입니다.

    `generate_answer_node`, `answer_draft`, `evidence_docs` 저장 흐름과 연결됩니다.
    """

    # 한국어 고객 답변 초안 (_MAX_DRAFT_LENGTH 초과 시 state.errors에 기록됨)
    answer_draft: str
    # 인용한 documents_chunks.chunk_id 목록 — rag_retrieve_node 결과에 없는 ID는 필터링된다
    evidence_doc_ids: list[str] = Field(default_factory=list)


class UrgentDraftResponse(PromptModel):
    """긴급 운영자 알림 초안 LLM 응답 모델입니다.

    `urgent_draft_node`와 `notification_logs`에 남길 운영 알림 메시지에 연결됩니다.
    """

    # 티켓 ID, route, 위험도, 필요 조치를 포함한 한국어 운영자 알림 메시지
    urgent_draft: str


class SafetyReviewResponse(PromptModel):
    """승인 게이트의 안전성 검수 LLM 응답 모델입니다.

    `approval_gate_node`, `safety_results`, 승인/검수/긴급 알림 분기에 연결됩니다.
    """

    # True: 근거·안전성 기준을 모두 통과 (approval_route="approved" 조건)
    approved: bool
    # True: 초안 내용이 검색 근거와 일치 (factuality_score=1.0 으로 저장됨)
    evidence_matched: bool
    # True: 사실 왜곡 의심 (hallucination_score=1.0; approved=False 를 강제해야 한다)
    hallucination_detected: bool
    # True: 게임 정책 위반 → approval_gate_node가 urgent_alert를 강제한다
    policy_violation_detected: bool
    # True: 위험·차별·명예훼손 등 부적절한 표현 포함 (toxicity_score=1.0 으로 저장됨)
    unsafe_expression_detected: bool
    # 판단 근거 목록 — safety_results.safety_reason 에 줄바꿈으로 합쳐 저장됨
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResponse(PromptModel):
    """운영자 검수 결정을 보조하는 LLM 응답 모델입니다.

    `human_review_node`와 승인, 반려, 편집 후속 노드 선택에 연결됩니다.
    """

    # approved / reject / edit 중 하나
    # edit: 소폭 수정으로 초안을 살릴 수 있을 때 — edited_answer 를 반드시 제공해야 한다
    # reject: 재라우팅 후 초안을 재생성해야 할 때 — retry_routing_node로 분기
    decision: HumanDecision
    # 결정 이유 — reject 시 retry_reason 으로 다음 query_router/analyze_ticket 프롬프트에 주입됨
    reason: str
    # edit 결정 시 수정된 답변 텍스트 (edit 이외 결정에서는 None 허용)
    edited_answer: str | None = None


# ─── 시스템 프롬프트 ───────────────────────────────────────────────────────────
# 모든 LLM 호출에 공통으로 사용되는 역할 정의 및 데이터 출처 제한 지침
# "DB/LLM context 이외의 데이터를 만들어내지 말 것"을 명시해 hallucination을 억제한다
SYSTEM_PROMPT = """You are an operation workflow assistant for a game customer-support system.
Use only the ticket, database context, and retrieved evidence provided in the prompt.
Return only JSON that matches the requested schema.
Do not invent user data, payment state, refund state, item delivery state, policy text, or incident status."""


# ─── QUERY_ROUTER_PROMPT ──────────────────────────────────────────────────────
# query_router 노드에서 사용: 문의 내용을 7개 업무 유형 중 하나로 분류
# 허용값 목록을 직접 나열해 LLM이 허용 범위 밖의 값을 반환할 가능성을 낮춘다
# {state_json}: render_state(current) 결과 — 티켓 제목·본문·사용자 메타데이터 포함
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


# ─── ANALYSIS_PROMPT ──────────────────────────────────────────────────────────
# analyze_ticket 노드에서 사용: route 분류 + DB context를 바탕으로 위험도·목표 route 분석
# urgent_alert 기준을 명확히 기술해 불필요한 에스컬레이션을 방지한다
# {state_json}: render_state(current) — query_route, context(업무 DB 데이터) 포함
ANALYSIS_PROMPT = """Analyze the ticket using the selected route and database context.

Set target_route to urgent_alert only when the case needs immediate operator attention, such as critical risk, outage, abuse escalation, policy violation, payment/refund risk, or missing authoritative evidence for a high-impact decision.
Otherwise set target_route to rag_reply.

Ticket and context:
{state_json}"""


# ─── ANSWER_PROMPT ────────────────────────────────────────────────────────────
# generate_answer_node 에서 사용: 검색 근거와 DB context를 기반으로 한국어 답변 초안 작성
# "Use database context only when it belongs to this ticket/user/account" 규칙:
#   다른 사용자의 결제·환불 데이터를 답변에 노출하는 것을 막기 위한 제약
# {state_json}: render_state(current) — retrieved_docs, context, analysis 포함
ANSWER_PROMPT = """Write a Korean customer-support answer draft grounded in retrieved evidence and database context.

Rules:
- Answer directly and politely.
- Use database context only when it belongs to this ticket/user/account.
- Cite evidence by returning evidence_doc_ids.
- If evidence is insufficient, say what should be checked by an operator.

Ticket, context, analysis, and evidence:
{state_json}"""


# ─── URGENT_PROMPT ────────────────────────────────────────────────────────────
# urgent_draft_node 에서 사용: 즉각 운영자 확인이 필요한 케이스의 알림 초안 작성
# 티켓 ID, route, 위험도, 필요 조치를 포함하도록 지정해 운영자가 빠르게 판단할 수 있게 한다
# {state_json}: render_state(current) — ticket, analysis (risk_level, required_actions) 포함
URGENT_PROMPT = """Write a concise Korean urgent alert draft for an operator.

Include ticket id, route, risk level, risk reason, relevant database context, and required actions.

Workflow state:
{state_json}"""


# ─── SAFETY_PROMPT ────────────────────────────────────────────────────────────
# approval_gate_node 에서 사용: 초안의 안전성·근거성을 4개 항목으로 검수
# 각 boolean 필드가 SafetyReviewResponse와 1:1 대응한다
# {state_json}: render_state(current) — answer_draft, retrieved_docs, analysis 포함
SAFETY_PROMPT = """Review the answer draft before final publication.

Check:
- Whether the draft is grounded in retrieved evidence and database context.
- Whether hallucination is present.
- Whether policy violation is present.
- Whether unsafe, defamatory, threatening, discriminatory, or overly definitive language is present.

Workflow state:
{state_json}"""


# ─── HUMAN_REVIEW_PROMPT ──────────────────────────────────────────────────────
# human_review_node 에서 사용: 운영자 검수 결정을 보조하는 추천 결정 생성
# edit: 소폭 수정으로 초안을 살릴 수 있을 때 — edited_answer 필드를 반드시 채워야 한다
# reject: 재라우팅 후 재생성이 필요할 때 (reason이 retry_reason으로 주입됨)
# {state_json}: render_state(current) — answer_draft, safety_result, analysis 포함
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
    import json

    # model_dump_json은 Pydantic v2에서 ensure_ascii 파라미터를 지원하지 않는다.
    # model_dump()로 dict를 얻고 json.dumps()에서 ensure_ascii=False를 적용한다.
    # exclude_none=True: None 필드를 제외해 프롬프트 토큰을 절약하고 LLM 혼란을 줄인다
    # ensure_ascii=False: 한국어 문자를 유니코드 이스케이프 없이 그대로 출력해 가독성을 높인다
    return json.dumps(
        state.model_dump(exclude_none=True),
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def render_documents(documents: list[EvidenceDocument]) -> str:
    """검색된 근거 문서 목록을 프롬프트용 문자열로 직렬화합니다.

    `EvidenceDocument` 목록을 답변 생성 프롬프트와 근거 검수 기능에 연결합니다.
    """

    return "\n".join(document.model_dump_json(exclude_none=True, ensure_ascii=False) for document in documents)
