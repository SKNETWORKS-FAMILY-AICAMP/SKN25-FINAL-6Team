"""CS 답변 생성 agent.

분석이 끝난 카페 문의를 대상으로 근거를 조회하고, LangChain LCEL
체인과 Pydantic 모델로 답변 초안과 safety 결과를 만든 뒤 workflow
테이블에 저장한다.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from agents.retrieval import EvidenceItem, RetrievalRouter
from common.db.connection import db_connection


SafetyAction = Literal["ready_for_review", "human_review", "fixed_answer"]


class AnswerTarget(BaseModel):
    """qa_ticket과 최신 ticket_analysis를 합친 답변 생성 대상."""

    model_config = ConfigDict(extra="allow")

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


class RetrievalStrategy(BaseModel):
    """routing_target을 실행 가능한 근거 조회 옵션으로 정규화한다."""

    routing_target: str
    use_documents: bool = False
    use_operation_logs: bool = False
    fixed_answer: bool = False


class DraftContext(BaseModel):
    """LCEL 답변 초안 생성에 필요한 모든 입력."""

    ticket: AnswerTarget
    analysis: AnswerTarget
    evidence_docs: list[EvidenceItem] = Field(default_factory=list)
    regeneration_reason: str | None = None


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


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


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
    action: SafetyAction = "ready_for_review"
    reason = "grounded_draft_ready_for_operator_review"
    if not has_evidence:
        action = "human_review"
        reason = "missing_evidence"
    if toxicity >= 0.5 or policy >= 0.5:
        action = "fixed_answer"
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
    """분석 대상 1건을 초안과 safety 결과로 바꾸는 LCEL 체인."""

    return (
        RunnableLambda(AnswerTarget.model_validate)
        | RunnableLambda(_build_draft_context)
        | RunnableParallel(context=RunnablePassthrough(), draft_text=RunnableLambda(_compose_draft_text), safety=RunnableLambda(_evaluate_context_safety))
        | RunnableLambda(lambda parts: AnswerGenerationResult.model_validate(parts))
    )


def build_regeneration_chain():
    """기존 근거와 운영자 재생성 사유를 새 초안으로 바꾸는 LCEL 체인."""

    return RunnableLambda(_build_regeneration_context) | RunnableLambda(_result_from_context)


ANSWER_CHAIN = build_answer_generation_chain()
REGENERATION_CHAIN = build_regeneration_chain()


def run_answer_agent() -> None:
    """답변 초안이 없는 카페 문의를 순차 처리한다."""

    targets = fetch_answer_target_tickets()
    for target in targets:
        process_answer_target(target)


def regenerate_agent(ticket_id: int | None = None, regeneration_reason: str | None = None) -> dict[str, object] | None:
    """운영자 재생성 사유를 기존 근거에 반영해 새 초안을 저장한다."""

    if ticket_id is None:
        return None
    limit = validate_regeneration_limit(ticket_id)
    if not limit["can_regenerate"]:
        return None

    context = fetch_regeneration_context(ticket_id)
    result = REGENERATION_CHAIN.invoke({"context": context, "regeneration_reason": regeneration_reason or ""})
    draft = save_answer_draft(result.context.ticket.model_dump(), result.context.analysis.model_dump(), result.draft_text)
    saved_evidence = save_evidence_docs(int(draft["draft_id"]), [item.model_dump() for item in result.context.evidence_docs])
    safety = result.safety.model_copy(update={"retry_count": int(limit["retry_count"]) + 1})
    saved_safety = save_safety_results(int(draft["draft_id"]), safety.model_dump())
    return {"draft": draft, "evidence_docs": saved_evidence, "safety": saved_safety, "retry_count": safety.retry_count}


def fetch_answer_target_tickets() -> list[dict[str, object]]:
    """분석은 끝났지만 초안과 최종 답변이 없는 naver_cafe 문의를 조회한다."""

    limit = int(os.environ.get("CS_AUTO_ANSWER_BATCH_LIMIT", "30"))
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_all(
                cur,
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


def process_answer_target(target: dict[str, object]) -> None:
    """문의 1건의 근거 조회, 초안 저장, safety 저장, 상태 갱신을 수행한다."""

    result = ANSWER_CHAIN.invoke(target)
    draft = save_answer_draft(result.context.ticket.model_dump(), result.context.analysis.model_dump(), result.draft_text)
    saved_evidence = save_evidence_docs(int(draft["draft_id"]), [item.model_dump() for item in result.context.evidence_docs])
    saved_safety = save_safety_results(int(draft["draft_id"]), result.safety.model_dump())
    route_by_safety_result(result.context.ticket.model_dump(), result.context.analysis.model_dump(), draft, saved_safety)


def select_retrieval_strategy(analysis: dict[str, object]) -> dict[str, object]:
    """routing_target을 retrieval 옵션으로 정규화한다."""

    routing_target = str(analysis.get("routing_target") or "fixed_answer")
    strategy = RetrievalStrategy(
        routing_target=routing_target,
        use_documents=routing_target in {"doc_only", "DB&DOC"},
        use_operation_logs=routing_target in {"DB_only", "DB&DOC"},
        fixed_answer=routing_target in {"fixed_answer", "human_review"},
    )
    return strategy.model_dump()


def collect_answer_evidence(
    ticket: dict[str, object],
    analysis: dict[str, object],
    strategy: dict[str, object],
) -> list[dict[str, object]]:
    """RetrievalRouter LCEL 체인으로 답변 근거를 가져온다."""

    return RetrievalRouter().retrieve_by_routing_target(ticket, {**analysis, **strategy})


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


def save_answer_draft(ticket: dict[str, object], analysis: dict[str, object], draft_text: str) -> dict[str, object]:
    """answer_draft에 답변 초안을 저장한다."""

    target = AnswerTarget.model_validate({**ticket, **analysis})
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft_id = _next_integer_id(cur, "answer_draft", "draft_id")
            cur.execute(
                """
                INSERT INTO answer_draft (draft_id, ticket_id, analysis_id, draft_text, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING draft_id, ticket_id, analysis_id, draft_text, created_at
                """,
                (draft_id, target.ticket_id, target.analysis_id, draft_text),
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
            safety_id = _next_integer_id(cur, "safety_results", "safety_id")
            cur.execute(
                """
                INSERT INTO safety_results (
                    safety_id,
                    draft_id,
                    hallucination_score,
                    toxicity_score,
                    policy_violation_score,
                    factuality_score,
                    checked_at,
                    safety_action,
                    safety_reason,
                    retry_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING safety_id, draft_id, safety_action, safety_reason, retry_count
                """,
                (
                    safety_id,
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

    action = str(safety_result.get("safety_action") or "human_review")
    next_status = "drafted" if action == "ready_for_review" else "human_review"
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
            if action == "fixed_answer" and analysis.get("analysis_id") is not None:
                cur.execute(
                    """
                    UPDATE ticket_analysis
                    SET routing_target = %s
                    WHERE analysis_id = %s
                    """,
                    ("fixed_answer", analysis["analysis_id"]),
                )


def validate_regeneration_limit(ticket_id: int) -> dict[str, object]:
    """ticket_id 기준 재생성 가능 횟수를 계산한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _fetch_one(
                cur,
                """
                SELECT COALESCE(MAX(s.retry_count), 0) AS retry_count
                FROM answer_draft d
                LEFT JOIN safety_results s ON s.draft_id = d.draft_id
                WHERE d.ticket_id = %s
                """,
                (ticket_id,),
            )
    retry_count = int(row.get("retry_count") or 0) if row else 0
    limit = int(os.environ.get("CS_AUTO_REGENERATION_LIMIT", "3"))
    return {"ticket_id": ticket_id, "retry_count": retry_count, "limit": limit, "can_regenerate": retry_count < limit}


def fetch_regeneration_context(ticket_id: int) -> dict[str, object]:
    """재생성에 필요한 기존 문의, 분석, 초안, 근거를 조회한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket = _fetch_one(cur, "SELECT * FROM qa_ticket WHERE ticket_id = %s", (ticket_id,)) or {}
            analysis = _fetch_one(
                cur,
                """
                SELECT *
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            ) or {}
            draft = _fetch_one(
                cur,
                """
                SELECT *
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            ) or {}
            evidence_docs = _fetch_all(
                cur,
                """
                SELECT source_type, source_id, evidence_text, relevance_score, retrieval_rank
                FROM evidence_docs
                WHERE draft_id = %s
                ORDER BY retrieval_rank ASC NULLS LAST, evidence_id ASC
                """,
                (draft.get("draft_id"),),
            ) if draft else []
    return {"ticket": ticket, "analysis": analysis, "draft": draft, "evidence_docs": evidence_docs}


def build_regeneration_prompt_context(context: dict[str, object], regeneration_reason: str) -> dict[str, object]:
    """기존 호출부 호환용 재생성 context builder."""

    return {
        "ticket": context.get("ticket") or {},
        "analysis": context.get("analysis") or {},
        "draft": context.get("draft") or {},
        "evidence_docs": context.get("evidence_docs") or [],
        "regeneration_reason": regeneration_reason,
    }


def save_final_response_after_approval(
    ticket_id: int,
    draft_id: int,
    final_text: str,
    safety_action: str | None = None,
) -> dict[str, object]:
    """운영자가 승인한 최종 답변을 final_response에 저장하고 티켓을 종료한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            response_id = _next_integer_id(cur, "final_response", "response_id")
            cur.execute(
                """
                INSERT INTO final_response (response_id, ticket_id, draft_id, final_text, safety_action, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id, ticket_id, draft_id, final_text, safety_action, created_at
                """,
                (response_id, ticket_id, draft_id, final_text, safety_action),
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


def mark_ticket_resolved_after_final_response(ticket_id: int, response_id: int) -> None:
    """final_response 생성 후 qa_ticket 상태를 resolved로 맞춘다."""

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("resolved", ticket_id),
            )
