"""CS answer draft generation agent skeleton.

This module orchestrates evidence collection and draft generation.
DB evidence is resolved through dbsearch and document evidence is resolved
through docsearch, while answer composition happens in this module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
import os
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

# backend 작업 디렉터리 기준으로 에이전트 모듈 경로를 맞춘다.
from agents.prompt_loader import load_prompt_template
from agents.tool.dbsearch import DbSearchRouter
from agents.tool.docsearch import DocumentRetriever
from common.db.connection import db_connection
from common.llm.client import get_chat_llm
from common.observability.langfuse import (
    build_trace_metadata,
    configure_langfuse,
    flush_langfuse,
    get_langchain_config,
    link_current_trace,
    observe_if_enabled,
    record_current_scores,
    trace_attributes,
)

configure_langfuse("cs-auto", default_tags=["cs-auto", "answer"])

logger = logging.getLogger(__name__)


RoutingTarget = Literal["DB_only", "doc_only", "DB&DOC", "fixed_answer"]
Category = Literal["payment", "refund", "account",  "gacha", "bug", "policy", "general"]
SafetyAction = Literal["approved", "fixed_answer"]

FIXED_ANSWER_FALLBACK_TEXT = "문의 내용을 확인했습니다. 정확한 안내를 위해 운영 검토 후 다시 안내드리겠습니다."
SAFETY_APPROVAL_THRESHOLD = 0.7


# qa_ticket와 ticket_analysis에서 초안 생성에 필요한 필드만 정규화하는 입력 모델이다.
# answer_agent 내부에서는 이 모델을 기준으로 retrieval과 draft 생성 단계를 연결한다.
class AnswerTarget(BaseModel):
    """Normalized input payload for answer draft generation."""

    model_config = ConfigDict(extra="ignore")

    ticket_id: int
    account_id: int | None = None
    user_id: int | None = None
    title: str = ""
    raw_query: str = ""
    source_type: str = ""
    status: str = ""
    inquiry_created_at: datetime | None = None
    assignee_admin_id: int | None = None

    analysis_id: int | None = None
    category: Category | str = "general"
    enriched_query: str = ""
    risk_level: str = ""
    sentiment: str = ""
    routing_target: RoutingTarget | str = "fixed_answer"
    summary: str = ""
    analyzed_at: datetime | None = None


# retrieval 결과와 초안 생성 메타데이터를 함께 묶는 중간 상태 모델이다.
# 증거 수집 단계와 초안 생성 단계를 느슨하게 분리하기 위해 사용한다.
class AnswerDraftContext(BaseModel):
    """Intermediate draft context after evidence collection."""

    ticket: AnswerTarget
    evidence_docs: list[dict[str, object]] = Field(default_factory=list)
    regeneration_reason: str = ""


# LLM이 생성한 고객 응답 초안과 안전성 메타데이터를 담는 출력 모델이다.
# 저장 단계에서는 이 모델을 그대로 answer_draft 테이블 입력으로 변환한다.
class AnswerDraftResult(BaseModel):
    """Structured answer draft output."""

    draft_text: str
    safety_label: Literal["safe", "review_required"] = "review_required"
    review_reason: str = ""
    used_evidence_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# safety_results 테이블의 점수 키를 그대로 사용하는 안전성 평가 결과 모델이다.
# 위험 점수와 근거성 점수를 함께 받아 후속 라우팅에서 fixed_answer 여부를 결정한다.
class AnswerSafetyResult(BaseModel):
    """Structured answer safety evaluation output."""

    hallucination_score: float = Field(ge=0.0, le=1.0)
    toxicity_score: float = Field(ge=0.0, le=1.0)
    policy_violation_score: float = Field(ge=0.0, le=1.0)
    factuality_score: float = Field(ge=0.0, le=1.0)
    safety_action: SafetyAction = "approved"
    safety_reason: str = ""
    retry_count: int = 0
    average_score: float = Field(default=0.0, ge=0.0, le=1.0)


ANSWER_DRAFT_PARSER = PydanticOutputParser(pydantic_object=AnswerDraftResult)
ANSWER_DRAFT_PROMPT = PromptTemplate(
    input_variables=["context_json"],
    partial_variables={"format_instructions": ANSWER_DRAFT_PARSER.get_format_instructions()},
    template=load_prompt_template("answer/draft_prompt.yaml"),
)
ANSWER_SAFETY_PARSER = PydanticOutputParser(pydantic_object=AnswerSafetyResult)
ANSWER_SAFETY_PROMPT = PromptTemplate(
    input_variables=["context_json"],
    partial_variables={"format_instructions": ANSWER_SAFETY_PARSER.get_format_instructions()},
    template=load_prompt_template("answer/safety_prompt.yaml"),
)

def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row[0])


# varchar(n) 컬럼 길이를 스키마에서 읽어서 저장 직전 문자열을 공통 정규화한다.
def _load_bounded_varchar_limits(
    cur: Any,
    table_name: str,
    schema_name: str = "public",
) -> dict[str, int]:
    cur.execute(
        """
        SELECT
            column_name,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND data_type = 'character varying'
          AND character_maximum_length IS NOT NULL
        """,
        (schema_name, table_name),
    )
    rows = cur.fetchall()
    return {
        str(column_name): int(max_length)
        for column_name, max_length in rows
        if column_name and max_length
    }


# None 은 그대로 두고, 문자열 제한이 있는 컬럼만 문자열 변환 및 길이 방어를 적용한다.
def _normalize_bounded_varchar_payload(
    payload: dict[str, object],
    varchar_limits: dict[str, int],
    table_name: str,
) -> dict[str, object]:
    normalized_payload = dict(payload)
    for column_name, max_length in varchar_limits.items():
        raw_value = normalized_payload.get(column_name)
        if raw_value is None:
            continue

        string_value = str(raw_value)
        if len(string_value) > max_length:
            logger.warning(
                "answer_agent truncating oversized varchar value before insert: table=%s column=%s max_length=%s original_length=%s",
                table_name,
                column_name,
                max_length,
                len(string_value),
            )
            string_value = string_value[:max_length]
        normalized_payload[column_name] = string_value
    return normalized_payload


class AnswerTargetRepository:
    """Load answer-draft targets from qa_ticket and ticket_analysis."""

    def fetch(self, ticket_id: int) -> AnswerTarget:
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        q.ticket_id,
                        q.account_id,
                        q.user_id,
                        COALESCE(q.title, '') AS title,
                        COALESCE(q.raw_query, '') AS raw_query,
                        COALESCE(q.source_type, '') AS source_type,
                        COALESCE(q.status, '') AS status,
                        q.inquiry_created_at,
                        q.assignee_admin_id,
                        a.analysis_id,
                        COALESCE(a.category, 'general') AS category,
                        COALESCE(a.enriched_query, '') AS enriched_query,
                        COALESCE(a.risk_level, '') AS risk_level,
                        COALESCE(a.sentiment, '') AS sentiment,
                        COALESCE(a.routing_target, 'fixed_answer') AS routing_target,
                        COALESCE(a.summary, '') AS summary,
                        a.analyzed_at
                    FROM qa_ticket q
                    LEFT JOIN ticket_analysis a ON a.ticket_id = q.ticket_id
                    WHERE q.ticket_id = %s
                    """,
                    (ticket_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        return AnswerTarget.model_validate(dict(row))


def fetch_undrafted_tickets() -> list[dict[str, object]]:
    """Load analyzed tickets that do not yet have an answer draft."""

    limit = int(os.environ.get("CS_AUTO_ANSWER_BATCH_LIMIT", "50"))
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    q.ticket_id
                FROM qa_ticket q
                JOIN ticket_analysis a ON a.ticket_id = q.ticket_id
                LEFT JOIN answer_draft d ON d.ticket_id = q.ticket_id
                WHERE d.draft_id IS NULL
                ORDER BY q.inquiry_created_at ASC NULLS LAST, q.ticket_id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def mark_answer_draft_completed(ticket_id: int) -> None:
    """Mark the ticket as having an AI draft ready for review."""

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("draft_generated", ticket_id),
            )


# routing_target에 따라 DB 검색과 문서 검색을 호출해 근거를 조합하는 서비스 클래스다.
# 실제 조합 책임은 answer_agent에 두고, 개별 검색 구현은 tool 하위 모듈에 위임한다.
class AnswerEvidenceCollector:
    """Collect evidence for answer drafting from DB and document search tools."""

    def __init__(self) -> None:
        self.db_router = DbSearchRouter()
        self.doc_retriever = DocumentRetriever()

    @observe_if_enabled(name="cs_auto_collect_answer_evidence", as_type="tool", tags=["feature:answer", "feature:evidence"])
    def collect(self, target: AnswerTarget) -> list[dict[str, object]]:
        link_current_trace(
            user_id=target.user_id,
            session_id=target.ticket_id,
            tags=["feature:answer", "feature:evidence"],
            metadata=build_trace_metadata(target.model_dump(), answer_stage="collect_evidence"),
            input_payload={"ticket_id": target.ticket_id, "routing_target": target.routing_target},
        )
        ticket = self._ticket_payload(target)
        analysis = self._analysis_payload(target)
        routing_target = str(target.routing_target or "fixed_answer")

        if routing_target == "DB_only":
            return self.collect_db_only(ticket, analysis)
        if routing_target == "doc_only":
            return self.collect_doc_only(ticket, analysis)
        if routing_target == "DB&DOC":
            return self.collect_db_and_doc(ticket, analysis)
        return self.collect_fixed_answer_context(analysis)

    def collect_db_only(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        result = self.db_router.run(ticket, analysis)
        return list(result.get("evidence") or [])

    def collect_doc_only(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        return self.doc_retriever.retrieve(ticket, analysis)

    def collect_db_and_doc(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        return [
            *self.collect_db_only(ticket, analysis),
            *self.collect_doc_only(ticket, analysis),
        ]

    def collect_fixed_answer_context(self, analysis: dict[str, object]) -> list[dict[str, object]]:
        return self.doc_retriever.retrieve_fixed_answer_context(analysis)

    def _ticket_payload(self, target: AnswerTarget) -> dict[str, object]:
        return {
            "ticket_id": target.ticket_id,
            "account_id": target.account_id,
            "user_id": target.user_id,
            "title": target.title,
            "raw_query": target.raw_query,
            "source_type": target.source_type,
            "status": target.status,
            "inquiry_created_at": target.inquiry_created_at,
            "assignee_admin_id": target.assignee_admin_id,
        }

    def _analysis_payload(self, target: AnswerTarget) -> dict[str, object]:
        return {
            "analysis_id": target.analysis_id,
            "category": target.category,
            "enriched_query": target.enriched_query,
            "risk_level": target.risk_level,
            "sentiment": target.sentiment,
            "routing_target": target.routing_target,
            "summary": target.summary,
            "analyzed_at": target.analyzed_at,
            "account_id": target.account_id,
            "user_id": target.user_id,
        }


# ticket, analysis, evidence를 바탕으로 고객 응답 초안을 생성하는 LLM 서비스 클래스다.
# 초안 생성과 안전성 판정을 하나의 structured output으로 받도록 스켈레톤을 구성한다.
class AnswerDraftGenerator:
    """Generate structured customer-facing answer drafts."""

    def __init__(self) -> None:
        llm = get_chat_llm()
        self.chain = (RunnableLambda(self._build_prompt_input)|ANSWER_DRAFT_PROMPT| llm | ANSWER_DRAFT_PARSER)

    def _build_prompt_input(self, context: AnswerDraftContext) -> dict[str, str]:
        evidence_docs = []
        for item in context.evidence_docs:
            evidence_docs.append(
                {
                    "source_type": item.get("source_type"),
                    "source_id": item.get("source_id"),
                    "evidence_text": str(item.get("evidence_text") or "")[:1000],
                    "relevance_score": item.get("relevance_score"),
                    "retrieval_rank": item.get("retrieval_rank"),
                }
            )

        payload = {
            "ticket_id": context.ticket.ticket_id,
            "title": context.ticket.title,
            "raw_query": context.ticket.raw_query,
            "category": context.ticket.category,
            "routing_target": context.ticket.routing_target,
            "summary": context.ticket.summary,
            "risk_level": context.ticket.risk_level,
            "sentiment": context.ticket.sentiment,
            "regeneration_reason": context.regeneration_reason,
            "evidence_docs": evidence_docs,
        }
        return {"context_json": json.dumps(payload, ensure_ascii=False)}

    @observe_if_enabled(name="cs_auto_generate_answer_draft_text", as_type="generation", tags=["feature:answer"])
    def generate(self, context: AnswerDraftContext) -> AnswerDraftResult:
        trace_metadata = build_trace_metadata(
            context.ticket.model_dump(),
            answer_stage="generate_draft",
            evidence_count=len(context.evidence_docs),
        )
        with trace_attributes(
            user_id=context.ticket.user_id,
            session_id=context.ticket.ticket_id,
            tags=["feature:answer"],
            metadata=trace_metadata,
        ):
            link_current_trace(
                user_id=context.ticket.user_id,
                session_id=context.ticket.ticket_id,
                tags=["feature:answer"],
                metadata=trace_metadata,
            )
            return AnswerDraftResult.model_validate(self.chain.invoke(context, config=get_langchain_config()))


# 생성된 초안과 근거를 바탕으로 safety_results 형식의 점수를 평가하는 LCEL 클래스다.
# 평균 점수가 임계값 이하이면 fixed_answer 경로로 강등하기 위한 중간 판정 역할을 한다.
class AnswerSafetyEvaluator:
    """Evaluate generated drafts with safety_results-compatible scoring."""

    def __init__(self) -> None:
        llm = get_chat_llm()
        self.chain = (
            RunnableLambda(self._build_prompt_input)| ANSWER_SAFETY_PROMPT | llm | ANSWER_SAFETY_PARSER )

    def _build_prompt_input(self, payload: dict[str, object]) -> dict[str, str]:
        context = AnswerDraftContext.model_validate(payload["context"])
        draft = AnswerDraftResult.model_validate(payload["draft"])
        evidence_docs = []
        for item in context.evidence_docs:
            evidence_docs.append(
                {
                    "source_type": item.get("source_type"),
                    "source_id": item.get("source_id"),
                    "evidence_text": str(item.get("evidence_text") or "")[:1000],
                    "relevance_score": item.get("relevance_score"),
                    "retrieval_rank": item.get("retrieval_rank"),
                }
            )

        payload = {
            "ticket_id": context.ticket.ticket_id,
            "title": context.ticket.title,
            "raw_query": context.ticket.raw_query,
            "category": context.ticket.category,
            "routing_target": context.ticket.routing_target,
            "summary": context.ticket.summary,
            "draft_text": draft.draft_text,
            "evidence_docs": evidence_docs,
        }
        return {"context_json": json.dumps(payload, ensure_ascii=False)}

    @observe_if_enabled(name="cs_auto_evaluate_answer_safety", as_type="generation", tags=["feature:answer", "feature:safety"])
    def evaluate(self, context: AnswerDraftContext, draft: AnswerDraftResult) -> AnswerSafetyResult:
        trace_metadata = build_trace_metadata(
            context.ticket.model_dump(),
            answer_stage="evaluate_safety",
            evidence_count=len(context.evidence_docs),
        )
        with trace_attributes(
            user_id=context.ticket.user_id,
            session_id=context.ticket.ticket_id,
            tags=["feature:answer", "feature:safety"],
            metadata=trace_metadata,
        ):
            link_current_trace(
                user_id=context.ticket.user_id,
                session_id=context.ticket.ticket_id,
                tags=["feature:answer", "feature:safety"],
                metadata=trace_metadata,
                input_payload={"ticket_id": context.ticket.ticket_id, "draft_text_length": len(draft.draft_text or "")},
            )
            result = AnswerSafetyResult.model_validate(
                self.chain.invoke({"context": context, "draft": draft}, config=get_langchain_config())
            )
        average_score = (
            (1 - result.hallucination_score)
            + (1 - result.toxicity_score)
            + (1 - result.policy_violation_score)
            + result.factuality_score
        ) / 4
        average_score = round(float(average_score), 4)
        safety_action: SafetyAction = "approved" if average_score > SAFETY_APPROVAL_THRESHOLD else "fixed_answer"
        scored_result = result.model_copy(
            update={
                "average_score": average_score,
                "safety_action": safety_action,
            }
        )
        record_current_scores(
            {
                "hallucination_score": scored_result.hallucination_score,
                "toxicity_score": scored_result.toxicity_score,
                "policy_violation_score": scored_result.policy_violation_score,
                "factuality_score": scored_result.factuality_score,
                "average_score": scored_result.average_score,
                "safety_approved": scored_result.safety_action == "approved",
            },
            comments={
                "safety_approved": scored_result.safety_reason or "",
            },
        )
        return scored_result


# safety 평가 결과를 반영해 초안을 유지하거나 fixed_answer 문안으로 대체하는 클래스다.
# 안전성 평균이 낮을 때는 고객에게 보수적인 검토 안내 문안만 전달하도록 강등한다.
class AnswerSafetyRouter:
    """Apply safety evaluation result to the generated draft."""

    def route(self, context: AnswerDraftContext, draft: AnswerDraftResult, safety: AnswerSafetyResult) -> AnswerDraftResult:
        if safety.safety_action != "fixed_answer":
            return draft.model_copy(
                update={
                    "safety_label": "safe",
                    "metadata": {
                        **draft.metadata,
                        "safety_action": safety.safety_action,
                        "safety_average_score": safety.average_score,
                    },
                }
            )

        fixed_answer_text = self._fixed_answer_text(context)
        return draft.model_copy(
            update={
                "draft_text": fixed_answer_text,
                "safety_label": "review_required",
                "review_reason": safety.safety_reason or "low_safety_average_score",
                "metadata": {
                    **draft.metadata,
                    "safety_action": "fixed_answer",
                    "safety_average_score": safety.average_score,
                },
            }
        )

    def _fixed_answer_text(self, context: AnswerDraftContext) -> str:
        for item in context.evidence_docs:
            if str(item.get("source_type") or "") == "fixed_answer":
                text = str(item.get("evidence_text") or "").strip()
                if text:
                    return text
        return FIXED_ANSWER_FALLBACK_TEXT


# 생성된 초안과 근거를 answer_draft, evidence_docs 테이블에 저장하는 저장소 스켈레톤이다.
# 실제 INSERT/UPSERT SQL은 이후 API 및 스키마에 맞춰 구체화하면 된다.
class AnswerDraftRepository:
    """Persist answer drafts and linked evidence rows."""

    @observe_if_enabled(name="cs_auto_save_answer_draft", as_type="tool", tags=["feature:answer", "feature:persistence"])
    def save_draft(self, target: AnswerTarget, result: AnswerDraftResult) -> int:
        with db_connection() as conn:
            with conn.cursor() as cur:
                draft_id = _next_integer_id(cur, "answer_draft", "draft_id")
                cur.execute(
                    """
                    INSERT INTO answer_draft (
                        draft_id,
                        ticket_id,
                        analysis_id,
                        draft_text,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING draft_id
                    """,
                    (
                        draft_id,
                        target.ticket_id,
                        target.analysis_id,
                        result.draft_text,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise ValueError("Failed to create answer_draft row")
        draft_id = int(row[0])
        link_current_trace(
            user_id=target.user_id,
            session_id=target.ticket_id,
            tags=["feature:answer", "feature:persistence"],
            metadata=build_trace_metadata(
                target.model_dump(),
                answer_stage="save_draft",
                draft_id=draft_id,
            ),
            output_payload={"draft_id": draft_id},
        )
        return draft_id

    def save_evidence_docs(self, draft_id: int, evidence_docs: list[dict[str, object]]) -> None:
        if not evidence_docs:
            return

        with db_connection() as conn:
            with conn.cursor() as cur:
                for evidence in evidence_docs:
                    cur.execute(
                        """
                        INSERT INTO evidence_docs (
                            draft_id,
                            source_type,
                            source_id,
                            evidence_text,
                            relevance_score,
                            retrieval_rank
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            draft_id,
                            evidence.get("source_type"),
                            evidence.get("source_id"),
                            evidence.get("evidence_text"),
                            evidence.get("relevance_score"),
                            evidence.get("retrieval_rank"),
                        ),
                    )

    def save_safety_results(self, draft_id: int, safety: AnswerSafetyResult) -> int:
        with db_connection() as conn:
            with conn.cursor() as cur:
                safety_id = _next_integer_id(cur, "safety_results", "safety_id")
                varchar_limits = _load_bounded_varchar_limits(cur, "safety_results")
                # safety_results 의 문자열 컬럼은 스키마 기준으로 길이를 맞춘 뒤 저장한다.
                insert_payload = _normalize_bounded_varchar_payload(
                    payload={
                        "safety_action": safety.safety_action,
                        "safety_reason": safety.safety_reason,
                    },
                    varchar_limits=varchar_limits,
                    table_name="safety_results",
                )
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
                    RETURNING safety_id
                    """,
                    # (
                    #     safety_id,
                    #     draft_id,
                    #     safety.hallucination_score,
                    #     safety.toxicity_score,
                    #     safety.policy_violation_score,
                    #     safety.factuality_score,
                    #     safety.safety_action,
                    #     safety.safety_reason,
                    #     safety.retry_count,
                    # )
                    (
                        safety_id,
                        draft_id,
                        safety.hallucination_score,
                        safety.toxicity_score,
                        safety.policy_violation_score,
                        safety.factuality_score,
                        insert_payload.get("safety_action"),
                        insert_payload.get("safety_reason"),
                        safety.retry_count,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise ValueError("Failed to create safety_results row")
        return int(row[0])


# 답변 초안 생성 전체 흐름을 묶는 상위 오케스트레이터 클래스다.
# 대상 조회, 근거 수집, 초안 생성, 저장 단계를 순서대로 실행하는 진입점 역할을 한다.
class AnswerAgent:
    """Orchestrate answer draft generation end to end."""

    def __init__(self) -> None:
        self.target_repository = AnswerTargetRepository()
        self.evidence_collector = AnswerEvidenceCollector()
        self.draft_generator = AnswerDraftGenerator()
        self.safety_evaluator = AnswerSafetyEvaluator()
        self.safety_router = AnswerSafetyRouter()
        self.draft_repository = AnswerDraftRepository()

    @observe_if_enabled(name="cs_auto_generate_answer_draft", as_type="chain", tags=["feature:answer"])
    def generate_answer_draft(self, ticket_id: int) -> dict[str, object]:
        target = self.target_repository.fetch(ticket_id)
        trace_metadata = build_trace_metadata(target.model_dump(), answer_stage="generate_answer_draft")
        with trace_attributes(
            user_id=target.user_id,
            session_id=target.ticket_id,
            tags=["feature:answer"],
            metadata=trace_metadata,
        ):
            link_current_trace(
                user_id=target.user_id,
                session_id=target.ticket_id,
                tags=["feature:answer"],
                metadata=trace_metadata,
                input_payload={"ticket_id": ticket_id},
            )
            evidence_docs = self.evidence_collector.collect(target)
            context = AnswerDraftContext(ticket=target, evidence_docs=evidence_docs)
            draft_result = self.draft_generator.generate(context)
            safety_result = self.safety_evaluator.evaluate(context, draft_result)
            result = self.safety_router.route(context, draft_result, safety_result)

            draft_id = self.draft_repository.save_draft(target, result)
            self.draft_repository.save_evidence_docs(draft_id, evidence_docs)
            safety_id = self.draft_repository.save_safety_results(draft_id, safety_result)

            result_payload = {
                "ticket_id": target.ticket_id,
                "draft_id": draft_id,
                "safety_id": safety_id,
                "draft_text": result.draft_text,
                "safety_label": result.safety_label,
                "review_reason": result.review_reason,
                "evidence_docs": evidence_docs,
                "safety": safety_result.model_dump(),
                "metadata": result.metadata,
            }
            link_current_trace(
                user_id=target.user_id,
                session_id=target.ticket_id,
                tags=["feature:answer", "feature:safety", "feature:persistence"],
                metadata=build_trace_metadata({**target.model_dump(), **result_payload}),
                output_payload={
                    "ticket_id": target.ticket_id,
                    "draft_id": draft_id,
                    "safety_id": safety_id,
                    "safety_label": result_payload["safety_label"],
                },
            )
            return result_payload


@observe_if_enabled(name="cs_auto_run_answer_agent", as_type="chain", tags=["feature:answer"])
def run_answer_agent() -> None:
    """Generate answer drafts for analyzed tickets that do not have one yet."""
    try:
        agent = AnswerAgent()
        targets = fetch_undrafted_tickets()
        for target in targets:
            ticket_id = int(target["ticket_id"])
            agent.generate_answer_draft(ticket_id)
            mark_answer_draft_completed(ticket_id)
    finally:
        flush_langfuse()
