"""CS 답변 생성 agent.

분석이 끝난 카페 문의를 대상으로 근거를 조회하고, LangChain LCEL
체인과 Pydantic 모델로 답변 초안과 safety 결과를 만든 뒤 테이블에 저장한다.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from agents.retrieval import EvidenceItem, RetrievalRouter
from common.db.connection import db_connection


"""qa_ticket과 최신 ticket_analysis를 합쳐, 답변 초안 생성에 필요한 문의의 정보를 정리한다"""

# Input and output models shared across generation, safety, and persistence.
class AnswerTarget(BaseModel):

    model_config = ConfigDict(extra="ignore") # 다른 필드 들어오면 무시한다..

    ticket_id: int
    account_id: int | None = None
    user_id: int | None = None
    title: str | None = ""
    raw_query: str | None = ""
    source_type: str | None = ""
    status: str | None = ""
    analysis_id: int | None = None
    category: str | None = "general"
    enriched_query: str | None = ""
    risk_level: str | None = "LOW"
    sentiment: str | None = "neutral"
    routing_target: str | None = "fixed_answer"
    summary: str | None = ""

"""
LCEL 답변 초안 생성에 필요한 모든 입력.
"""
class DraftContext(BaseModel):

    ticket: AnswerTarget
    analysis: AnswerTarget
    evidence_docs: list[EvidenceItem] = Field(default_factory=list)
    regeneration_reason: str | None = None


SafetyAction = Literal["approved","rejected"]

class SafetyResult(BaseModel):
    """safety_results 테이블에 저장할 검증 결과."""

    hallucination_score: float = Field(ge=0.0, le=1.0)
    toxicity_score: float = Field(ge=0.0, le=1.0)
    policy_violation_score: float = Field(ge=0.0, le=1.0)
    factuality_score: float = Field(ge=0.0, le=1.0)
    safety_action: SafetyAction
    safety_reason: str
    retry_count: int = 0


class AnswerGenerationResult(BaseModel):
    """LCEL 답변 체인의 출력 모델."""

    context: DraftContext
    draft_text: str
    safety: SafetyResult


# Small text helpers used while composing the operator draft.
def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    # workflow write 테이블은 기본 sequence가 없을 수 있어 명시 ID를 계산한다.
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row["next_id"])


def _safe_text(value: object, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _evidence_bullets(evidence_docs: list[EvidenceItem]) -> str:
    if not evidence_docs:
        return "- 자동 조회된 근거가 없어 운영자 확인이 필요합니다."
    return "\n".join(
        f"- [{item.source_type}] {_safe_text(item.evidence_text, 500)}"
        for item in evidence_docs[:5]
    )


# Draft generation: turn ticket, analysis, and evidence into one reply text.
def _compose_draft_text(context: DraftContext) -> str:
    """근거와 분석 결과를 한국어 CS 응대 초안으로 조립한다."""

    title = _safe_text(context.ticket.title or "문의", 120)
    body = _safe_text(context.ticket.raw_query, 700)
    summary = _safe_text(context.analysis.summary, 700)
    evidence = _evidence_bullets(context.evidence_docs)
    reason = (
        f"\n\n재생성 요청 반영 사항:\n- {_safe_text(context.regeneration_reason, 500)}"
        if context.regeneration_reason
        else ""
    )
    return (
        "안녕하세요. 게임 고객지원팀입니다.\n\n"
        f"접수하신 문의({title})를 확인했습니다.\n"
        f"문의 내용 요약: {body}\n\n"
        f"분석 결과: {summary}\n\n"
        "확인한 근거:\n"
        f"{evidence}"
        f"{reason}\n\n"
        "위 근거를 기준으로 처리 가능 여부를 검토 중입니다. "
        "결제, 지급, 계정 상태처럼 추가 확인이 필요한 항목은 운영 기록 확인 후 안내드리겠습니다.\n\n"
        "감사합니다."
    )


# Safety scoring: decide whether the draft can move forward automatically.
def _evaluate_context_safety(context: DraftContext) -> SafetyResult:
    """근거 존재 여부와 금칙 표현 기반으로 초안 안전성을 점검한다."""

    has_evidence = bool(context.evidence_docs)
    draft_text = _compose_draft_text(context)
    toxic_terms = ("멍청", "바보", "꺼져", "책임 없음")
    policy_terms = ("무조건 환불", "무조건 지급", "확률 조작 확정", "보상 보장")
    toxicity = 0.6 if any(term in draft_text for term in toxic_terms) else 0.0
    policy = 0.7 if any(term in draft_text for term in policy_terms) else 0.0
    hallucination = 0.15 if has_evidence else 0.6
    factuality = 0.9 if has_evidence else 0.45
    action: SafetyAction = "approved"
    reason = "grounded_draft_ready_for_operator_review"
    if not has_evidence:
        action = "rejected"
        reason = "missing_evidence"
    if toxicity >= 0.5 or policy >= 0.5:
        action = "rejected"
        reason = "unsafe_expression_detected"
    return SafetyResult(
        hallucination_score=hallucination,
        toxicity_score=toxicity,
        policy_violation_score=policy,
        factuality_score=factuality,
        safety_action=action,
        safety_reason=reason,
        retry_count=0,
    )


# Context builders: collect the raw inputs needed to regenerate the same draft.
def _build_draft_context(target: AnswerTarget) -> DraftContext:
    strategy = select_retrieval_strategy(target.model_dump())
    evidence = collect_answer_evidence(target.model_dump(), target.model_dump(), strategy)
    evidence_items = [EvidenceItem.model_validate(item) for item in evidence]
    return DraftContext(ticket=target, analysis=target, evidence_docs=evidence_items)


def _build_regeneration_context(parts: dict[str, object]) -> DraftContext:
    context = parts["context"]
    reason = str(parts.get("regeneration_reason") or "")
    ticket = AnswerTarget.model_validate(context.get("ticket") or {})
    analysis = AnswerTarget.model_validate({**ticket.model_dump(), **(context.get("analysis") or {})})
    evidence_items = [EvidenceItem.model_validate(item) for item in context.get("evidence_docs") or []]
    return DraftContext(ticket=ticket, analysis=analysis, evidence_docs=evidence_items, regeneration_reason=reason)


def _result_from_context(context: DraftContext) -> AnswerGenerationResult:
    return AnswerGenerationResult(
        context=context,
        draft_text=_compose_draft_text(context),
        safety=_evaluate_context_safety(context),
    )


def build_answer_generation_chain():
    """Build the LCEL chain for first-pass answer generation."""

    return (
        RunnableLambda(AnswerTarget.model_validate)
        | RunnableLambda(_build_draft_context)
        | RunnableParallel(
            context=RunnablePassthrough(),
            draft_text=RunnableLambda(_compose_draft_text),
            safety=RunnableLambda(_evaluate_context_safety),
        )
        | RunnableLambda(lambda parts: AnswerGenerationResult.model_validate(parts))
    )


def build_regeneration_chain():
    """Build the LCEL chain for regeneration from existing context."""

    return RunnableLambda(_build_regeneration_context) | RunnableLambda(_result_from_context)


ANSWER_CHAIN = build_answer_generation_chain()
REGENERATION_CHAIN = build_regeneration_chain()


# Public wrappers over the LCEL chains.
def generate_answer_result(target: dict[str, object]) -> AnswerGenerationResult:
    return ANSWER_CHAIN.invoke(target)


def generate_regeneration_result(
    context: dict[str, object],
    regeneration_reason: str | None = None,
) -> AnswerGenerationResult:
    return REGENERATION_CHAIN.invoke(
        {
            "context": context,
            "regeneration_reason": regeneration_reason or "",
        }
    )


# Airflow 배치 진입점: 초안이 필요한 티켓을 읽어 1차 답변 초안을 생성한다.
def run_answer_agent() -> None:
    """답변 초안이 없는 카페 문의를 순차 처리한다."""

    targets = fetch_answer_target_tickets()
    for target in targets:
        process_answer_target(target)


# Airflow 배치 작업 단위: 분석 완료된 티켓 1건으로 초안을 만들고 저장한다.
def process_answer_target(target: dict[str, object]) -> None:
    """문의 1건의 근거 조회, 초안 저장, safety 저장, 상태 갱신을 수행한다."""

    result = generate_answer_result(target)
    draft = save_answer_draft(result.context.ticket.model_dump(), result.context.analysis.model_dump(), result.draft_text)
    saved_evidence = save_evidence_docs(int(draft["draft_id"]), [item.model_dump() for item in result.context.evidence_docs])
    saved_safety = save_safety_results(int(draft["draft_id"]), result.safety.model_dump())
    route_by_safety_result(result.context.ticket.model_dump(), result.context.analysis.model_dump(), draft, saved_safety)


# 프론트 재생성 진입점: 기존 근거와 재생성 사유로 새 초안을 다시 만든다.
def regenerate_agent(ticket_id: int | None = None, regeneration_reason: str | None = None) -> dict[str, object] | None:
    """운영자 재생성 사유를 기존 근거에 반영해 새 초안을 저장한다."""

    if ticket_id is None:
        return None
    limit = validate_regeneration_limit(ticket_id)
    if not limit["can_regenerate"]:
        return None

    context = fetch_regeneration_context(ticket_id)
    result = generate_regeneration_result(context, regeneration_reason)
    draft = save_answer_draft(result.context.ticket.model_dump(), result.context.analysis.model_dump(), result.draft_text)
    saved_evidence = save_evidence_docs(int(draft["draft_id"]), [item.model_dump() for item in result.context.evidence_docs])
    safety = result.safety.model_copy(update={"retry_count": int(limit["retry_count"]) + 1})
    saved_safety = save_safety_results(int(draft["draft_id"]), safety.model_dump())
    return {"draft": draft, "evidence_docs": saved_evidence, "safety": saved_safety, "retry_count": safety.retry_count}


# Retrieval routing: convert routing_target into concrete lookup options.
def select_retrieval_strategy(analysis: dict[str, object]) -> dict[str, object]:
    """routing_target을 retrieval 옵션으로 정규화한다."""

    routing_target = str(analysis.get("routing_target") or "fixed_answer")
    return {
        "routing_target": routing_target,
        "use_documents": routing_target in {"doc_only", "DB&DOC"},
        "use_operation_logs": routing_target in {"DB_only", "DB&DOC"},
        "fixed_answer": routing_target in {"fixed_answer"},
    }


def collect_answer_evidence(
    ticket: dict[str, object],
    analysis: dict[str, object],
    strategy: dict[str, object],
) -> list[dict[str, object]]:
    """RetrievalRouter LCEL 체인으로 답변 근거를 가져온다."""

    return RetrievalRouter().retrieve_by_routing_target(ticket, {**analysis, **strategy})


# Thin wrappers kept for direct unit testing of draft text and safety logic.
def generate_answer_draft_text(
    ticket: dict[str, object],
    analysis: dict[str, object],
    evidence_docs: list[dict[str, object]],
    regeneration_reason: str | None = None,
) -> str:
    """기존 호출부 호환용 초안 생성 helper."""

    target = AnswerTarget.model_validate({**ticket, **analysis})
    context = DraftContext(
        ticket=target,
        analysis=target,
        evidence_docs=[EvidenceItem.model_validate(item) for item in evidence_docs],
        regeneration_reason=regeneration_reason,
    )
    return _compose_draft_text(context)


# Airflow 배치 대상 조회용 DB 함수다.
def fetch_answer_target_tickets() -> list[dict[str, object]]:
    """분석은 끝났지만 초안과 최종 답변이 없는 naver_cafe 문의를 조회한다."""

    limit = int(os.environ.get("CS_AUTO_ANSWER_BATCH_LIMIT", "30"))
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.account_id,
                    t.user_id,
                    t.title,
                    t.raw_query,
                    t.source_type,
                    t.status,
                    t.inquiry_created_at,
                    a.analysis_id,
                    a.category,
                    a.responder_type,
                    a.enriched_query,
                    a.risk_level,
                    a.sentiment,
                    a.routing_target,
                    a.summary,
                    a.analyzed_at
                FROM qa_ticket t
                JOIN LATERAL (
                    SELECT *
                    FROM ticket_analysis ta
                    WHERE ta.ticket_id = t.ticket_id
                    ORDER BY ta.analyzed_at DESC NULLS LAST, ta.analysis_id DESC
                    LIMIT 1
                ) a ON TRUE
                LEFT JOIN answer_draft d ON d.ticket_id = t.ticket_id
                LEFT JOIN final_response fr ON fr.ticket_id = t.ticket_id
                WHERE t.source_type = 'naver_cafe'
                  AND d.draft_id IS NULL
                  AND fr.response_id IS NULL
                  AND COALESCE(t.status, '') <> 'resolved'
                ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


# Airflow 초안 생성과 프론트 재생성에서 공통으로 쓰는 저장 함수들이다.
def save_answer_draft(ticket: dict[str, object], analysis: dict[str, object], draft_text: str) -> dict[str, object]:
    """answer_draft에 답변 초안을 저장한다."""

    target = AnswerTarget.model_validate({**ticket, **analysis})
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO answer_draft (ticket_id, analysis_id, draft_text)
                VALUES (%s, %s, %s)
                RETURNING draft_id, ticket_id, analysis_id, draft_text, created_at
                """,
                (target.ticket_id, target.analysis_id, draft_text),
            )
            row = cur.fetchone()
    return dict(row)


def save_evidence_docs(draft_id: int, evidence_docs: list[dict[str, object]]) -> list[dict[str, object]]:
    """초안에 사용한 근거를 evidence_docs에 저장한다."""

    saved: list[dict[str, object]] = []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for evidence in evidence_docs:
                item = EvidenceItem.model_validate(evidence)
                evidence_id = _next_integer_id(cur, "evidence_docs", "evidence_id")
                cur.execute(
                    """
                    INSERT INTO evidence_docs (
                        evidence_id,
                        draft_id,
                        source_type,
                        source_id,
                        evidence_text,
                        relevance_score,
                        retrieval_rank
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING evidence_id, draft_id, source_type, source_id, evidence_text, relevance_score, retrieval_rank
                    """,
                    (
                        evidence_id,
                        draft_id,
                        item.source_type,
                        str(item.source_id) if item.source_id is not None else None,
                        item.evidence_text,
                        item.relevance_score,
                        item.retrieval_rank,
                    ),
                )
                saved.append(dict(cur.fetchone()))
    return saved


def evaluate_answer_safety(draft: dict[str, object], evidence_docs: list[dict[str, object]]) -> dict[str, object]:
    """기존 호출부 호환용 safety 평가 helper."""

    target = AnswerTarget.model_validate({"ticket_id": int(draft.get("ticket_id") or 0), "title": "", "raw_query": ""})
    context = DraftContext(
        ticket=target,
        analysis=target,
        evidence_docs=[EvidenceItem.model_validate(item) for item in evidence_docs],
    )
    return _evaluate_context_safety(context).model_dump()


def save_safety_results(draft_id: int, safety_result: dict[str, object]) -> dict[str, object]:
    """safety_results에 초안 검증 결과를 저장한다."""

    safety = SafetyResult.model_validate(safety_result)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO safety_results (
                    draft_id,
                    hallucination_score,
                    toxicity_score,
                    policy_violation_score,
                    factuality_score,
                    safety_action,
                    safety_reason,
                    retry_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING safety_id, draft_id, safety_action, safety_reason, retry_count
                """,
                (
                    draft_id,
                    safety.hallucination_score,
                    safety.toxicity_score,
                    safety.policy_violation_score,
                    safety.factuality_score,
                    safety.safety_action,
                    safety.safety_reason,
                    safety.retry_count,
                ),
            )
            row = cur.fetchone()
    return dict(row)


def route_by_safety_result(
    ticket: dict[str, object],
    analysis: dict[str, object],
    draft: dict[str, object],
    safety_result: dict[str, object],
) -> None:
    """safety 결과에 따라 티켓 상태와 라우팅 상태를 갱신한다."""

    action = str(safety_result.get("safety_action") or "rejected")
    reason = str(safety_result.get("safety_reason") or "")
    next_status = "drafted" if action == "approved" else "human_review"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                  AND COALESCE(status, '') <> 'resolved'
                """,
                (next_status, ticket["ticket_id"]),
            )
            if reason == "unsafe_expression_detected" and analysis.get("analysis_id") is not None:
                cur.execute(
                    """
                    UPDATE ticket_analysis
                    SET routing_target = %s
                    WHERE analysis_id = %s
                    """,
                    ("fixed_answer", analysis["analysis_id"]),
                )


# 프론트 재생성 지원 함수들이다. 재시도 제한을 검사하고 최신 초안 문맥을 읽는다.
def validate_regeneration_limit(ticket_id: int) -> dict[str, object]:
    """ticket_id 기준 재생성 가능 횟수를 계산한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(s.retry_count), 0) AS retry_count
                FROM answer_draft d
                LEFT JOIN safety_results s ON s.draft_id = d.draft_id
                WHERE d.ticket_id = %s
                """,
                (ticket_id,),
            )
            fetched = cur.fetchone()
            row = dict(fetched) if fetched is not None else None
    retry_count = int(row.get("retry_count") or 0) if row else 0
    limit = int(os.environ.get("CS_AUTO_REGENERATION_LIMIT", "3"))
    return {"ticket_id": ticket_id, "retry_count": retry_count, "limit": limit, "can_regenerate": retry_count < limit}


def fetch_regeneration_context(ticket_id: int) -> dict[str, object]:
    """재생성에 필요한 기존 문의, 분석, 초안, 근거를 조회한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM qa_ticket WHERE ticket_id = %s", (ticket_id,))
            ticket_row = cur.fetchone()
            ticket = dict(ticket_row) if ticket_row is not None else {}
            cur.execute(
                """
                SELECT *
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            )
            analysis_row = cur.fetchone()
            analysis = dict(analysis_row) if analysis_row is not None else {}
            cur.execute(
                """
                SELECT *
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            )
            draft_row = cur.fetchone()
            draft = dict(draft_row) if draft_row is not None else {}
            evidence_docs: list[dict[str, object]] = []
            if draft:
                cur.execute(
                    """
                    SELECT source_type, source_id, evidence_text, relevance_score, retrieval_rank
                    FROM evidence_docs
                    WHERE draft_id = %s
                    ORDER BY retrieval_rank ASC NULLS LAST, evidence_id ASC
                    """,
                    (draft.get("draft_id"),),
                )
                evidence_docs = [dict(row) for row in cur.fetchall()]
    return {"ticket": ticket, "analysis": analysis, "draft": draft, "evidence_docs": evidence_docs}


def save_final_response_after_approval(
    ticket_id: int,
    draft_id: int,
    final_text: str,
    safety_action: str | None = None,
) -> dict[str, object]:
    """운영자가 승인한 최종 답변을 final_response에 저장하고 티켓을 종료한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO final_response (ticket_id, draft_id, final_text, safety_action)
                VALUES (%s, %s, %s, %s)
                RETURNING response_id, ticket_id, draft_id, final_text, safety_action, created_at
                """,
                (ticket_id, draft_id, final_text, safety_action),
            )
            row = cur.fetchone()
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("resolved", ticket_id),
            )
    return dict(row)
