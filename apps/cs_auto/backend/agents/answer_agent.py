"""CS 답변 생성 agent.

분석이 끝난 카페 문의를 대상으로 근거를 조회하고, LangChain LCEL
체인과 Pydantic 모델로 답변 초안과 safety 결과를 만든 뒤 테이블에 저장한다.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Literal

from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, ConfigDict, Field

from agents.retrieval import EvidenceItem, RetrievalRouter
from common.db.connection import db_connection
from common.llm.client import invoke_structured_llm


SafetyAction = Literal["ready_for_review", "human_review", "fixed_answer"]

# Input and output models shared across generation, safety, and persistence.
class AnswerTarget(BaseModel):
    """qa_ticket과 최신 ticket_analysis를 합친 답변 생성 대상."""

    model_config = ConfigDict(extra="ignore") # 다른 필드 들어오면 무시한다..

    ticket_id: int
    account_id: int | None = None
    user_id: int | None = None
    title: str | None = ""
    raw_query: str | None = ""
    source_type: str | None = ""
    status: str | None = ""
    inquiry_created_at: datetime | None = None
    session_id: int | None = None
    responder_type: str | None = "agent"
    assignee_id: str | None = None
    assignee_admin_id: int | None = None
    analysis_id: int | None = None
    category: str | None = "general"
    enriched_query: str | None = ""
    risk_level: str | None = "LOW"
    sentiment: str | None = "neutral"
    routing_target: str | None = "fixed_answer"
    summary: str | None = ""
    analyzed_at: datetime | None = None

"""
LCEL 답변 초안 생성에 필요한 모든 입력.
"""
class DraftContext(BaseModel):
    """LCEL 답변 초안 생성에 필요한 모든 입력."""

    ticket: AnswerTarget
    analysis: AnswerTarget
    evidence_docs: list[EvidenceItem] = Field(default_factory=list)
    regeneration_reason: str | None = None
    evidence_is_stale: bool = False


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
    """LCEL 답변 체인의 출력 모델.

    ANSWER_CHAIN과 REGENERATION_CHAIN은 모두 이 모델을 반환한다.
    """

    context: DraftContext
    draft_text: str
    safety: SafetyResult


class DraftLLMResult(BaseModel):
    """LLM 기반 초안 생성 결과.

    review_required_reason은 생성된 초안을 상담원이 검토해야 하는 이유를
    짧게 보존하기 위한 필드이며, 초안 본문에는 필수로 드러내지 않는다.
    """

    draft_text: str = Field(min_length=1)
    review_required_reason: str | None = None


# Small text helpers used while composing the operator draft.
def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    # workflow write 테이블은 기본 sequence가 없을 수 있어 명시 ID를 계산한다.
    # table_name/id_column을 SQL 문자열에 넣어야 하므로, 외부 입력을 절대 받지 않고
    # 내부에서 허용한 테이블/컬럼 조합만 통과시킨다.
    if ALLOWED_ID_TARGETS.get(table_name) != id_column:
        raise ValueError(f"Unsupported id target: {table_name}.{id_column}")
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row["next_id"])


def get_answer_agent_contract() -> dict[str, object]:
    """답변생성 에이전트의 책임과 LCEL 모델 계약을 반환한다.

    테스트와 운영 문서에서 현재 역할을 명확히 확인할 수 있게 하는 읽기 전용 계약이다.
    """

    return {
        "role_steps": list(ANSWER_AGENT_ROLE_STEPS),
        "answer_chain": {
            "input_model": ANSWER_CHAIN_INPUT_MODEL,
            "output_model": ANSWER_CHAIN_OUTPUT_MODEL,
        },
        "regeneration_chain": {
            "input_model": REGENERATION_CHAIN_INPUT_MODEL,
            "output_model": REGENERATION_CHAIN_OUTPUT_MODEL,
        },
        "retrieval": {
            "strategy_by_target": RETRIEVAL_STRATEGY_BY_TARGET,
            "evidence_required_fields": list(EVIDENCE_REQUIRED_FIELDS),
            "empty_evidence_policy": "human_review",
        },
        "safety": {
            "scoring_policy": SAFETY_SCORING_POLICY,
            "threshold_environment": {
                "toxicity": "CS_AUTO_TOXICITY_THRESHOLD",
                "policy_violation": "CS_AUTO_POLICY_VIOLATION_THRESHOLD",
                "hallucination": "CS_AUTO_HALLUCINATION_THRESHOLD",
                "factuality": "CS_AUTO_FACTUALITY_THRESHOLD",
            },
            "default_thresholds": DEFAULT_SAFETY_THRESHOLDS,
            "llm_factuality_enabled": False,
            "action_to_ticket_status": SAFETY_ACTION_TO_TICKET_STATUS,
        },
        "status": {
            "standard_ticket_statuses": list(STANDARD_TICKET_STATUSES),
            "frontend_status_contract": FRONTEND_STATUS_CONTRACT,
            "drafted_is_ready_for_operator_review": True,
        },
        "regeneration": {
            "input": ["ticket_id", "regeneration_reason"],
            "limit_env": "CS_AUTO_REGENERATION_LIMIT",
            "default_limit": DEFAULT_REGENERATION_LIMIT,
            "evidence_policy": REGENERATION_EVIDENCE_POLICY,
            "creates_new_answer_draft": True,
            "creates_new_safety_results": True,
            "logs_admin_event": True,
        },
        "persistence": {
            "id_strategy": "locked_max_plus_one",
            "allowed_id_targets": ALLOWED_ID_TARGETS,
            "draft_evidence_safety_transaction": True,
        },
        "batch": ANSWER_BATCH_POLICY,
        "observability": ANSWER_OBSERVABILITY_POLICY,
        "privacy_security": PRIVACY_SECURITY_POLICY,
        "implementation_priorities": ANSWER_IMPLEMENTATION_PRIORITIES,
        "dependencies": {
            "local_agents": ["agents.retrieval"],
            "common_packages": ["common.db.connection"],
            "chatbot_code": False,
        },
    }


def _answer_batch_limit() -> int:
    raw_limit = os.environ.get("CS_AUTO_ANSWER_BATCH_LIMIT")
    if raw_limit is None:
        return DEFAULT_ANSWER_BATCH_LIMIT
    try:
        return max(1, int(raw_limit))
    except ValueError:
        return DEFAULT_ANSWER_BATCH_LIMIT


def _terminal_ticket_statuses() -> list[str]:
    configured = os.environ.get("CS_AUTO_ANSWER_TERMINAL_STATUSES")
    if not configured:
        return list(TERMINAL_TICKET_STATUSES)
    statuses = [status.strip().lower() for status in configured.split(",") if status.strip()]
    return statuses or list(TERMINAL_TICKET_STATUSES)


def _llm_draft_enabled() -> bool:
    """LLM 초안 생성 사용 여부.

    기본값은 false다. 배치 안정성과 테스트 재현성을 위해 명시적으로
    CS_AUTO_LLM_DRAFT_ENABLED=true를 준 환경에서만 LLM을 호출한다.
    """

    return os.environ.get("CS_AUTO_LLM_DRAFT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """환경변수 기반 threshold parser.

    잘못된 값이 들어오면 배치가 실패하지 않도록 기본값을 사용한다.
    """

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """환경변수 기반 integer parser.

    재생성 제한/근거 유효기간처럼 운영 정책값은 잘못 설정되어도 배치가
    중단되면 안 되므로 기본값으로 되돌린다.
    """

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return max(0, int(raw_value))
    except ValueError:
        return default


def _safety_thresholds() -> dict[str, float]:
    """운영 환경별로 조정 가능한 safety threshold를 반환한다."""

    return {
        "toxicity": _env_float("CS_AUTO_TOXICITY_THRESHOLD", DEFAULT_SAFETY_THRESHOLDS["toxicity"]),
        "policy_violation": _env_float("CS_AUTO_POLICY_VIOLATION_THRESHOLD", DEFAULT_SAFETY_THRESHOLDS["policy_violation"]),
        "hallucination": _env_float("CS_AUTO_HALLUCINATION_THRESHOLD", DEFAULT_SAFETY_THRESHOLDS["hallucination"]),
        "factuality": _env_float("CS_AUTO_FACTUALITY_THRESHOLD", DEFAULT_SAFETY_THRESHOLDS["factuality"]),
    }


def _standardize_evidence_items(evidence_docs: list[dict[str, object]]) -> list[EvidenceItem]:
    """RetrievalRouter 결과를 답변 생성 context용 EvidenceItem으로 표준화한다.

    retrieval.py의 DB 근거와 문서 근거는 모두 evidence_docs 저장에 바로 쓸 수
    있어야 하므로 source_type/source_id/evidence_text/relevance_score/retrieval_rank
    계약을 여기서 한 번 더 검증한다. source_id만 None을 허용하는 이유는 일부
    고정 안내 근거가 별도 원천 PK 없이 ticket_id 맥락으로만 생성될 수 있기 때문이다.
    """

    standardized: list[EvidenceItem] = []
    for index, raw_item in enumerate(evidence_docs, start=1):
        item = EvidenceItem.model_validate(raw_item)
        if not str(item.source_type or "").strip():
            raise ValueError("EvidenceItem.source_type is required")
        if not str(item.evidence_text or "").strip():
            raise ValueError("EvidenceItem.evidence_text is required")
        standardized.append(
            EvidenceItem(
                source_type=item.source_type,
                source_id=item.source_id,
                evidence_text=item.evidence_text,
                relevance_score=float(item.relevance_score),
                retrieval_rank=int(item.retrieval_rank or index),
            )
        )
    standardized.sort(key=lambda item: item.retrieval_rank)
    return standardized


def _evidence_review_required(evidence_docs: list[EvidenceItem]) -> bool:
    """상담원 검토 필요 여부를 초안 프롬프트에 명시하기 위한 정책 함수."""

    if not evidence_docs:
        return True
    return any(item.source_type in {"fixed_answer", "operation_gap"} for item in evidence_docs)


def _term_match_score(text: str, terms: tuple[str, ...], per_match: float, maximum: float) -> float:
    """금칙어/정책 위험어 매칭 점수를 0~maximum 범위로 계산한다."""

    matches = sum(1 for term in terms if term and term in text)
    return min(maximum, matches * per_match)


def _factuality_score_from_evidence(evidence_docs: list[EvidenceItem]) -> float:
    """근거 품질 기반 factuality 점수.

    - 근거 없음: 0.45로 낮게 시작한다.
    - fixed_answer: 실제 사실 근거가 아니라 운영자 확인 안내이므로 중간 이하로 둔다.
    - operation_gap: 중요한 운영 근거지만 자동 확정 근거가 아니라 검토 신호이므로 약간 보수적으로 둔다.
    - 일반 근거: 관련도와 근거 개수를 반영하되 최대 0.95로 제한한다.
    """

    if not evidence_docs:
        return 0.45
    if all(item.source_type == "fixed_answer" for item in evidence_docs):
        return 0.58

    max_relevance = max(float(item.relevance_score or 0.0) for item in evidence_docs)
    factuality = 0.65 + min(max_relevance, 1.0) * 0.25 + min(len(evidence_docs), 5) * 0.025
    if any(item.source_type == "operation_gap" for item in evidence_docs):
        factuality -= 0.08
    return round(max(0.0, min(0.95, factuality)), 4)


def _regeneration_limit() -> int:
    """운영자 재생성 허용 횟수.

    기본값은 3회이며 CS_AUTO_REGENERATION_LIMIT로 조정한다.
    """

    return _env_int("CS_AUTO_REGENERATION_LIMIT", DEFAULT_REGENERATION_LIMIT)


def _regeneration_evidence_max_age_days() -> int:
    """재생성 시 기존 근거를 재사용할 수 있는 최대 경과일."""

    return _env_int("CS_AUTO_REGENERATION_EVIDENCE_MAX_AGE_DAYS", DEFAULT_REGENERATION_EVIDENCE_MAX_AGE_DAYS)


def _is_regeneration_evidence_stale(draft_created_at: object) -> bool:
    """기존 근거의 stale 여부를 판단한다.

    evidence_docs에는 별도 created_at이 없으므로 최신 draft.created_at을 근거 스냅샷
    생성 시각으로 본다. created_at이 없으면 검토 안전성을 위해 stale로 간주한다.
    """

    if not isinstance(draft_created_at, datetime):
        return True
    return datetime.now() - draft_created_at.replace(tzinfo=None) > timedelta(days=_regeneration_evidence_max_age_days())


def _ticket_status_for_safety_action(action: str) -> str:
    """SafetyAction과 qa_ticket.status 전환 규칙.

    ready_for_review는 초안 검토 대기 상태인 drafted로 두고,
    human_review/fixed_answer는 운영자 확인이 필요한 상태이므로 human_review로 보낸다.
    """

    return SAFETY_ACTION_TO_TICKET_STATUS.get(action, TICKET_STATUS_HUMAN_REVIEW)


def _safe_text(value: object, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _mask_sensitive_text(value: object, limit: int = 1000) -> str:
    """LLM 프롬프트에 넣기 전 민감 식별자를 최소 마스킹한다.

    raw_query 자체는 답변 품질에 필요하므로 context에서 완전히 제거하지 않는다.
    대신 이메일, 거래/영수증처럼 보이는 긴 영문숫자 토큰, UID 표기값을 숨긴다.
    로그에는 이 함수 결과도 저장하지 않는다.
    """

    text = _safe_text(value, limit)
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email_masked]", text)
    text = re.sub(r"\b(?:txn|tx|transaction|receipt|order)[-_:#]?[A-Za-z0-9-]{6,}\b", "[payment_id_masked]", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Z0-9]{10,}\b", "[long_id_masked]", text)
    text = re.sub(r"\b(?:uid|UID|유저ID|회원ID)\s*[:=#-]?\s*[A-Za-z0-9_-]{4,}\b", "uid=[uid_masked]", text)
    return text


def _log_metadata(
    *,
    ticket_id: object = None,
    analysis_id: object = None,
    draft_id: object = None,
    evidence_count: object = None,
    safety_action: object = None,
    failure_reason: object = None,
) -> dict[str, object]:
    """admin_event_logs.metadata에 저장할 허용 필드만 구성한다.

    이 함수의 목적은 실수로 raw_query, evidence_text, transaction_id,
    refund_reason 같은 원문/민감값이 로그에 들어가는 경로를 막는 것이다.
    """

    metadata = {
        "ticket_id": ticket_id,
        "analysis_id": analysis_id,
        "draft_id": draft_id,
        "evidence_count": evidence_count,
        "safety_action": safety_action,
        "failure_reason": _safe_text(failure_reason, 300) if failure_reason else None,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _classify_answer_failure(exc: Exception, stage: str, strategy: dict[str, object] | None = None) -> str:
    """답변 생성 실패 원인을 운영 로그용 범주로 정규화한다.

    retrieval 내부 예외가 DB/문서 어느 쪽에서 왔는지 명확하지 않은 경우가 있어,
    실행 중이던 stage와 routing strategy를 함께 보고 보수적으로 분류한다.
    """

    message = str(exc).lower()
    if stage == "document_retrieval" or "document" in message or "embedding" in message or "vector" in message:
        return "document_retrieval_failed"
    if stage == "db_retrieval" or "psycopg" in message or "sql" in message or "database" in message:
        return "db_retrieval_failed"
    if stage == "retrieval" and strategy:
        if strategy.get("use_documents") and not strategy.get("use_operation_logs"):
            return "document_retrieval_failed"
        if strategy.get("use_operation_logs") and not strategy.get("use_documents"):
            return "db_retrieval_failed"
    if stage == "llm_generation":
        return "llm_generation_failed"
    if stage == "persistence":
        return "persistence_failed"
    return "answer_generation_failed"


def log_answer_generation_event(
    *,
    event_type: str,
    status: str,
    ticket_id: object = None,
    analysis_id: object = None,
    draft_id: object = None,
    evidence_count: object = None,
    safety_action: object = None,
    failure_reason: object = None,
) -> None:
    """답변 생성 티켓 단위 이벤트를 admin_event_logs에 남긴다.

    failed_queries는 자연어 SQL/검색 실패 원문 추적 성격이 강하므로 답변 생성
    agent의 운영 관측성은 admin_event_logs로 단일화한다.
    """

    numeric_ticket_id = int(ticket_id) if ticket_id is not None else None
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_event_logs (
                    ticket_id,
                    node_name,
                    event_type,
                    status,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    numeric_ticket_id,
                    "cs_auto_answer_agent",
                    event_type,
                    status,
                    Json(
                        _log_metadata(
                            ticket_id=ticket_id,
                            analysis_id=analysis_id,
                            draft_id=draft_id,
                            evidence_count=evidence_count,
                            safety_action=safety_action,
                            failure_reason=failure_reason,
                        )
                    ),
                ),
            )


def _evidence_bullets(evidence_docs: list[EvidenceItem]) -> str:
    if not evidence_docs:
        return "- 자동 조회된 근거가 없어 운영자 확인이 필요합니다."
    return "\n".join(
        f"- [{item.source_type}] {_safe_text(item.evidence_text, 500)}"
        for item in evidence_docs[:5]
    )


def _operation_and_document_evidence(context: DraftContext) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    """근거를 DB 근거와 문서 근거로 나눈다.

    프롬프트에서 '실제 운영 기록'과 '정책/FAQ 문서'의 역할을 분리해 주면
    LLM이 정책 문서를 실제 결제 상태처럼 오해하는 일을 줄일 수 있다.
    """

    operation_prefixes = {"payments", "refunds", "item_delivery_logs", "gacha_logs", "operation_db", "operation_gap"}
    operation: list[EvidenceItem] = []
    documents: list[EvidenceItem] = []
    for item in context.evidence_docs:
        if item.source_type in operation_prefixes:
            operation.append(item)
        else:
            documents.append(item)
    return operation, documents


def _format_prompt_evidence(items: list[EvidenceItem]) -> str:
    """LLM 프롬프트에 넣을 근거 문자열을 민감정보 최소 형태로 만든다."""

    if not items:
        return "- 없음"
    lines = []
    for item in items[:8]:
        prompt_source_id = "internal" if item.source_type in {"payments", "refunds", "item_delivery_logs", "gacha_logs", "operation_db", "operation_gap"} else item.source_id
        lines.append(
            (
                f"- rank={item.retrieval_rank}; "
                f"source_type={item.source_type}; "
                f"source_id={prompt_source_id}; "
                f"score={item.relevance_score:.4f}; "
                f"text={_mask_sensitive_text(item.evidence_text, 700)}"
            )
        )
    return "\n".join(lines)


def _build_draft_user_prompt(context: DraftContext) -> str:
    """답변 초안 생성 프롬프트를 구성한다.

    필수 포함 항목:
    - 문의 제목
    - 문의 원문
    - 분석 요약
    - 카테고리
    - 라우팅 결과
    - DB 근거
    - 문서 근거
    - 상담원 검토 필요 여부
    """

    operation_evidence, document_evidence = _operation_and_document_evidence(context)
    review_required = _evidence_review_required(context.evidence_docs)
    regeneration = (
        f"\n재생성 요청 사항:\n{_mask_sensitive_text(context.regeneration_reason, 500)}\n"
        if context.regeneration_reason
        else ""
    )
    return (
        "다음 정보를 바탕으로 한국어 CS 답변 초안을 작성하십시오.\n\n"
        f"문의 제목:\n{_mask_sensitive_text(context.ticket.title, 200)}\n\n"
        f"문의 원문:\n{_mask_sensitive_text(context.ticket.raw_query, 1200)}\n\n"
        f"분석 요약:\n{_mask_sensitive_text(context.analysis.summary, 1000)}\n\n"
        f"카테고리: {_safe_text(context.analysis.category, 80)}\n"
        f"라우팅 결과: {_safe_text(context.analysis.routing_target, 80)}\n"
        f"위험도: {_safe_text(context.analysis.risk_level, 80)}\n"
        f"감성: {_safe_text(context.analysis.sentiment, 80)}\n"
        f"상담원 검토 필요 여부: {'예' if review_required else '아니오'}\n"
        f"기존 근거 오래됨 여부: {'예' if context.evidence_is_stale else '아니오'}\n"
        f"{regeneration}\n"
        "DB 근거:\n"
        f"{_format_prompt_evidence(operation_evidence)}\n\n"
        "문서/정책 근거:\n"
        f"{_format_prompt_evidence(document_evidence)}\n\n"
        "작성 조건:\n"
        "- 고객에게 바로 확정 통보하는 문장이 아니라 상담원이 검토할 초안으로 작성하십시오.\n"
        "- 결제/환불/지급/가챠 상태는 DB 근거에 있는 사실만 말하십시오.\n"
        "- 정책 안내는 문서/정책 근거에 있는 범위에서만 말하십시오.\n"
        "- 근거가 부족하면 담당자 확인 후 안내한다는 보수적 문장을 포함하십시오.\n"
        "- 5문단 이내로 간결하게 작성하십시오."
    )


# Draft generation: turn ticket, analysis, and evidence into one reply text.
def _compose_draft_text(context: DraftContext) -> str:
    """근거와 분석 결과를 한국어 CS 응대 초안으로 조립한다.

    이 함수는 LLM 실패 또는 비활성화 시 항상 동작해야 하는 deterministic
    fallback이다. 운영 배치가 외부 API 장애 때문에 멈추지 않도록 보존한다.
    """

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


def _generate_draft_text(context: DraftContext) -> str:
    """LLM 기반 초안 생성 후 실패 시 템플릿 fallback으로 되돌린다."""

    fallback_text = _compose_draft_text(context)
    if not _llm_draft_enabled():
        return fallback_text

    try:
        result = invoke_structured_llm(
            system_prompt=LLM_DRAFT_SYSTEM_PROMPT,
            user_prompt=_build_draft_user_prompt(context),
            response_model=DraftLLMResult,
        )
        return _safe_text(result.draft_text, 4000) or fallback_text
    except Exception as exc:  # noqa: BLE001 - LLM 장애 시 템플릿 fallback을 유지한다.
        log_answer_generation_event(
            event_type=ANSWER_OBSERVABILITY_POLICY["events"]["llm_fallback"],
            status="failed",
            ticket_id=context.ticket.ticket_id,
            analysis_id=context.analysis.analysis_id,
            evidence_count=len(context.evidence_docs),
            failure_reason=_classify_answer_failure(exc, "llm_generation"),
        )
        return fallback_text


# Safety scoring: decide whether the draft can move forward automatically.
def _evaluate_context_safety(context: DraftContext) -> SafetyResult:
    """근거 존재 여부, 금칙 표현, 정책 단정 표현 기반으로 초안 안전성을 점검한다.

    LLM factuality는 현재 기본 경로에 붙이지 않는다. 외부 API 장애가 있어도
    답변 생성 배치가 안정적으로 돌아야 하므로, 규칙 기반 점수를 source of truth로 둔다.
    """

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
        action = "rejected"
        reason = "missing_evidence"
    if toxicity >= 0.5 or policy >= 0.5:
        action = "fixed_answer"
        reason = "unsafe_expression_detected"
    elif hallucination >= thresholds["hallucination"] or factuality < thresholds["factuality"]:
        action = "human_review"
        reason = "low_factuality_or_high_hallucination"

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
    evidence_items = _standardize_evidence_items(evidence)
    return DraftContext(ticket=target, analysis=target, evidence_docs=evidence_items)


def _build_regeneration_context(parts: dict[str, object]) -> DraftContext:
    context = parts["context"]
    reason = str(parts.get("regeneration_reason") or "")
    ticket = AnswerTarget.model_validate(context.get("ticket") or {})
    analysis = AnswerTarget.model_validate({**ticket.model_dump(), **(context.get("analysis") or {})})
    evidence_items = _standardize_evidence_items(context.get("evidence_docs") or [])
    return DraftContext(
        ticket=ticket,
        analysis=analysis,
        evidence_docs=evidence_items,
        regeneration_reason=reason,
        evidence_is_stale=bool(context.get("evidence_is_stale")),
    )


def _result_from_context(context: DraftContext) -> AnswerGenerationResult:
    return AnswerGenerationResult(
        context=context,
        draft_text=_generate_draft_text(context),
        safety=_evaluate_context_safety(context),
    )


def build_answer_generation_chain():
    """Build the LCEL chain for first-pass answer generation."""

    return (
        RunnableLambda(AnswerTarget.model_validate)
        | RunnableLambda(_build_draft_context)
        | RunnableParallel(context=RunnablePassthrough(), draft_text=RunnableLambda(_compose_draft_text), safety=RunnableLambda(_evaluate_context_safety))
        | RunnableLambda(lambda parts: AnswerGenerationResult.model_validate(parts))
    )


def build_regeneration_chain():
    """Build the LCEL chain for regeneration from existing context."""

    return RunnableLambda(_build_regeneration_context) | RunnableLambda(_result_from_context)


ANSWER_CHAIN = build_answer_generation_chain()
REGENERATION_CHAIN = build_regeneration_chain()


def run_answer_agent() -> None:
    """답변 초안이 없는 카페 문의를 순차 처리한다."""

    targets = fetch_answer_target_tickets()
    processed = 0
    failed = 0
    failures: list[dict[str, object]] = []
    for target in targets:
        ticket_id = target.get("ticket_id")
        try:
            process_answer_target(target)
            processed += 1
        except Exception as exc:  # noqa: BLE001 - 배치는 티켓 단위 실패를 기록하고 계속 진행한다.
            failed += 1
            failure = {
                "ticket_id": ticket_id,
                "failure_reason": _classify_answer_failure(exc, "answer_generation"),
            }
            failures.append(failure)
            log_answer_ticket_failure(failure)

    result = {
        "target_count": len(targets),
        "processed_count": processed,
        "failed_count": failed,
        "failures": failures[:20],
    }
    log_answer_batch_event(result, status="partial_failed" if failed else "success")
    return result


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
    result = REGENERATION_CHAIN.invoke({"context": context, "regeneration_reason": regeneration_reason or ""})
    draft = save_answer_draft(result.context.ticket.model_dump(), result.context.analysis.model_dump(), result.draft_text)
    saved_evidence = save_evidence_docs(int(draft["draft_id"]), [item.model_dump() for item in result.context.evidence_docs])
    safety = result.safety.model_copy(update={"retry_count": int(limit["retry_count"]) + 1})
    persisted = persist_answer_generation_result(
        result.model_copy(update={"safety": safety}),
        route_ticket=False,
    )
    log_regeneration_event(
        ticket_id=ticket_id,
        previous_draft_id=context.get("draft", {}).get("draft_id") if isinstance(context.get("draft"), dict) else None,
        new_draft_id=persisted["draft"].get("draft_id") if isinstance(persisted.get("draft"), dict) else None,
        regeneration_reason=regeneration_reason or "",
        retry_count=safety.retry_count,
        evidence_is_stale=bool(context.get("evidence_is_stale")),
    )
    return {**persisted, "retry_count": safety.retry_count}


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
    """분석은 끝났지만 초안과 최종 답변이 없는 CS 자동화 대상 문의를 조회한다.

    운영 기준:
    - 답변 생성은 네이버 카페 게시글 응대 전용이므로 source_type='naver_cafe'만 조회한다.
    - answer_draft가 이미 있는 티켓은 중복 초안 생성을 막기 위해 제외한다.
    - final_response가 이미 있는 티켓은 종료된 응답으로 보고 제외한다.
    - resolved/closed/done/cancelled/canceled 상태는 종료 상태로 보고 제외한다.
    - 최신 ticket_analysis는 analyzed_at DESC, analysis_id DESC 기준으로 선택한다.
    - 배치 처리량 기본값은 DEFAULT_ANSWER_BATCH_LIMIT(30)이다.
    """

    limit = _answer_batch_limit()
    terminal_statuses = _terminal_ticket_statuses()
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
                    t.session_id,
                    t.responder_type,
                    t.assignee_id,
                    t.assignee_admin_id,
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
                WHERE t.source_type = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM answer_draft d
                      WHERE d.ticket_id = t.ticket_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM final_response fr
                      WHERE fr.ticket_id = t.ticket_id
                  )
                  AND LOWER(COALESCE(t.status, '')) <> ALL(%s)
                ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                LIMIT %s
                """,
                (DEFAULT_ANSWER_SOURCE_TYPE, terminal_statuses, limit),
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


def save_answer_draft(ticket: dict[str, object], analysis: dict[str, object], draft_text: str) -> dict[str, object]:
    """answer_draft에 답변 초안을 저장한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _insert_answer_draft(cur, ticket, analysis, draft_text)


def _insert_evidence_docs(cur: Any, draft_id: int, evidence_docs: list[dict[str, object]]) -> list[dict[str, object]]:
    """문서 근거와 DB 근거를 evidence_docs 실제 컬럼에 맞춰 저장한다."""

    saved: list[dict[str, object]] = []
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


def save_evidence_docs(draft_id: int, evidence_docs: list[dict[str, object]]) -> list[dict[str, object]]:
    """초안에 사용한 근거를 evidence_docs에 저장한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _insert_evidence_docs(cur, draft_id, evidence_docs)


def evaluate_answer_safety(draft: dict[str, object], evidence_docs: list[dict[str, object]]) -> dict[str, object]:
    """기존 호출부 호환용 safety 평가 helper."""

    target = AnswerTarget.model_validate({"ticket_id": int(draft.get("ticket_id") or 0), "title": "", "raw_query": ""})
    context = DraftContext(
        ticket=target,
        analysis=target,
        evidence_docs=_standardize_evidence_items(evidence_docs),
    )
    return _evaluate_context_safety(context).model_dump()


def _insert_safety_results(cur: Any, draft_id: int, safety_result: dict[str, object]) -> dict[str, object]:
    """safety_results 실제 컬럼에 맞춰 검증 결과를 insert한다."""

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


def save_safety_results(draft_id: int, safety_result: dict[str, object]) -> dict[str, object]:
    """safety_results에 초안 검증 결과를 저장한다."""

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _insert_safety_results(cur, draft_id, safety_result)


def _route_by_safety_result_with_cursor(
    cur: Any,
    ticket: dict[str, object],
    analysis: dict[str, object],
    safety_result: dict[str, object],
) -> None:
    """safety 결과에 따른 상태 전이를 현재 트랜잭션 안에서 실행한다."""

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


def route_by_safety_result(
    ticket: dict[str, object],
    analysis: dict[str, object],
    draft: dict[str, object],
    safety_result: dict[str, object],
) -> None:
    """safety 결과에 따라 티켓 상태와 라우팅 상태를 갱신한다."""

    with db_connection() as conn:
        with conn.cursor() as cur:
            _route_by_safety_result_with_cursor(cur, ticket, analysis, safety_result)


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
    limit = _regeneration_limit()
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
