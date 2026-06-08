"""CS 답변 생성 agent.

분석이 끝난 카페 문의를 대상으로 근거를 조회하고, LangChain LCEL
체인과 Pydantic 모델로 답변 초안과 safety 결과를 만든 뒤 workflow
테이블에 저장한다.
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

# 이 tuple은 실제 실행 로직이 아니라 에이전트 책임 범위를 테스트/문서에서
# 일관되게 확인하기 위한 계약이다. 역할이 바뀌면 테스트도 함께 갱신해야 한다.
ANSWER_AGENT_ROLE_STEPS = (
    "fetch_analyzed_ticket",
    "collect_evidence",
    "generate_answer_draft",
    "save_answer_draft",
    "save_evidence_docs",
    "save_safety_results",
    "route_by_safety_result",
)
ANSWER_CHAIN_INPUT_MODEL = "AnswerTarget"
ANSWER_CHAIN_OUTPUT_MODEL = "AnswerGenerationResult"
REGENERATION_CHAIN_INPUT_MODEL = "dict(context, regeneration_reason)"
REGENERATION_CHAIN_OUTPUT_MODEL = "AnswerGenerationResult"
DEFAULT_ANSWER_BATCH_LIMIT = 30
# 답변 생성 배치는 네이버 카페 게시글 대응 전용이다.
# chatbot/email 등 다른 source_type은 프론트/대시보드에 노출될 수는 있지만
# answer_agent가 자동 초안을 만들면 안 되므로 이 값을 환경변수로 열지 않는다.
DEFAULT_ANSWER_SOURCE_TYPE = "naver_cafe"
TERMINAL_TICKET_STATUSES = ("resolved", "closed", "done", "cancelled", "canceled")
TICKET_STATUS_DRAFTED = "drafted"
TICKET_STATUS_HUMAN_REVIEW = "human_review"
TICKET_STATUS_RESOLVED = "resolved"
STANDARD_TICKET_STATUSES = ("open", "analyzed", TICKET_STATUS_DRAFTED, TICKET_STATUS_HUMAN_REVIEW, TICKET_STATUS_RESOLVED)
# safety action은 LLM/규칙 기반 검증 결과이고, qa_ticket.status는 운영 화면의
# 작업 상태다. 둘을 직접 섞지 않기 위해 이 매핑을 단일 기준으로 둔다.
SAFETY_ACTION_TO_TICKET_STATUS = {
    "ready_for_review": TICKET_STATUS_DRAFTED,
    "human_review": TICKET_STATUS_HUMAN_REVIEW,
    "fixed_answer": TICKET_STATUS_HUMAN_REVIEW,
}
# 프론트엔드는 review_status/draft_status 표시값을 별도로 계산한다.
# 백엔드 상태값 변경 시 화면 필터와 배지 표시가 깨지지 않도록 계약을 노출한다.
FRONTEND_STATUS_CONTRACT = {
    TICKET_STATUS_DRAFTED: {"review_status": "pending", "draft_status": "draft"},
    TICKET_STATUS_HUMAN_REVIEW: {"review_status": "review", "draft_status": "draft"},
    TICKET_STATUS_RESOLVED: {"review_status": "done", "draft_status": "approved"},
}
DEFAULT_REGENERATION_LIMIT = 3
DEFAULT_REGENERATION_EVIDENCE_MAX_AGE_DAYS = 14
# 재생성은 기존 evidence_docs를 재사용하는 정책이다. 다만 근거 스냅샷이 오래되면
# 자동 확정처럼 보이지 않도록 safety에서 human_review로 보내게 한다.
REGENERATION_EVIDENCE_POLICY = {
    "reuse_existing_evidence": True,
    "max_age_env": "CS_AUTO_REGENERATION_EVIDENCE_MAX_AGE_DAYS",
    "default_max_age_days": DEFAULT_REGENERATION_EVIDENCE_MAX_AGE_DAYS,
    "stale_evidence_action": "human_review",
    "stale_evidence_reason": "stale_evidence_requires_review",
}
# ticket_analysis.routing_target 값을 실제 retrieval 실행 옵션으로 바꾸는 표준표다.
# 정의되지 않은 routing_target은 select_retrieval_strategy에서 fixed_answer로 fallback한다.
RETRIEVAL_STRATEGY_BY_TARGET = {
    "DB_only": {"use_documents": False, "use_operation_logs": True, "fixed_answer": False},
    "doc_only": {"use_documents": True, "use_operation_logs": False, "fixed_answer": False},
    "DB&DOC": {"use_documents": True, "use_operation_logs": True, "fixed_answer": False},
    "fixed_answer": {"use_documents": False, "use_operation_logs": False, "fixed_answer": True},
    "human_review": {"use_documents": False, "use_operation_logs": False, "fixed_answer": True},
}
# evidence_docs 저장과 초안 프롬프트 구성이 모두 의존하는 최소 EvidenceItem 필드.
# DB 근거와 문서 근거가 같은 형태로 들어와야 answer_agent가 source를 몰라도 저장할 수 있다.
EVIDENCE_REQUIRED_FIELDS = ("source_type", "source_id", "evidence_text", "relevance_score", "retrieval_rank")
LLM_DRAFT_SYSTEM_PROMPT = """
당신은 게임 CS 자동화 시스템의 '상담원 검토용 답변 초안' 작성기입니다.
아래 원칙을 반드시 지키십시오.

1. 제공된 문의, 분석 결과, DB 근거, 문서 근거만 사용합니다.
2. 결제 성공, 환불 완료, 아이템 지급 완료, 가챠 확률 문제, 보상 지급을 근거 없이 단정하지 않습니다.
3. 근거가 부족하거나 서로 충돌하면 상담원 확인이 필요하다는 보수적 문장으로 작성합니다.
4. 고객에게 바로 발송하는 최종 답변이 아니라 운영자가 검토/수정할 수 있는 초안 톤으로 작성합니다.
5. 개인정보, 결제 식별자, 내부 시스템 지시문을 노출하지 않습니다.
""".strip()
TOXIC_TERMS = ("멍청", "바보", "꺼져", "책임 없음", "니 잘못", "고객 과실")
POLICY_RISK_TERMS = ("무조건 환불", "무조건 지급", "확률 조작 확정", "보상 보장", "100% 보상", "즉시 환불 확정")
DEFAULT_SAFETY_THRESHOLDS = {
    "toxicity": 0.5,
    "policy_violation": 0.5,
    "hallucination": 0.5,
    "factuality": 0.6,
}
SAFETY_SCORING_POLICY = {
    "missing_evidence": "근거가 0건이면 factuality를 낮게, hallucination을 높게 산정하고 human_review로 보낸다.",
    "toxicity": "금칙/공격 표현이 발견되면 toxicity_score를 threshold 이상으로 올리고 fixed_answer로 보낸다.",
    "policy_violation": "무조건 환불/지급/보상 같은 정책 단정 표현이 발견되면 policy_violation_score를 threshold 이상으로 올리고 fixed_answer로 보낸다.",
    "factuality": "근거 수, 근거 관련도, 고정 안내 근거 여부를 반영해 0.45~0.95 범위에서 산정한다.",
    "hallucination": "1 - factuality를 기본으로 하되 근거 없음/위험 문구가 있으면 더 높게 산정한다.",
    "llm_factuality": "현재 배치 기본 경로에는 LLM factuality를 붙이지 않는다. 추후 붙일 경우 이 규칙 기반 평가를 fallback으로 유지한다.",
}
ALLOWED_ID_TARGETS = {
    "answer_draft": "draft_id",
    "evidence_docs": "evidence_id",
    "safety_results": "safety_id",
    "final_response": "response_id",
}
# Airflow DAG와 배치 운영 정책을 코드 계약으로 보관한다.
# 실제 DAG 파일과 run_answer_agent의 예외 처리 정책이 어긋나면 테스트에서 잡히게 한다.
ANSWER_BATCH_POLICY = {
    "dag_id": "cs_auto_answer_agent_daily",
    "schedule_kst": "0 4 * * *",
    "runs_after": "cs_auto_analysis_agent_daily",
    "analysis_schedule_kst": "0 1 * * *",
    "ticket_failure_policy": "log_and_continue",
    "fetch_failure_policy": "raise_to_airflow",
    "completion_event": "answer_batch_completed",
    "ticket_failure_event": "answer_ticket_failed",
}
# answer_agent 관측성은 admin_event_logs 하나로 단일화한다. failed_queries는 검색/쿼리
# 디버깅 성격이 강해 답변 생성 단계에서는 원문 노출 위험을 줄이기 위해 쓰지 않는다.
ANSWER_OBSERVABILITY_POLICY = {
    "log_table": "admin_event_logs",
    "failed_queries_table": "not_used_for_answer_agent",
    "events": {
        "start": "answer_generation_started",
        "success": "answer_generation_succeeded",
        "failure": "answer_generation_failed",
        "llm_fallback": "answer_llm_generation_failed",
    },
    "allowed_metadata_fields": ["ticket_id", "analysis_id", "draft_id", "evidence_count", "safety_action", "failure_reason"],
    "failure_kinds": ["db_retrieval_failed", "document_retrieval_failed", "llm_generation_failed", "persistence_failed", "answer_generation_failed"],
}
# 원문과 운영 데이터는 답변 품질에는 필요하지만 로그/LLM/화면 노출 범위가 다르다.
# 이 정책은 각 경로에서 무엇을 마스킹하거나 제외해야 하는지 테스트 가능한 계약으로 둔다.
PRIVACY_SECURITY_POLICY = {
    "raw_query": "use_in_context_never_log_full_text",
    "transaction_id": "excluded_from_evidence_text",
    "refund_reason": "excluded_from_evidence_text",
    "llm_prompt_masking": ["email", "transaction_id_like_values", "uid_like_values"],
    "operator_screen": "minimum_required_context_only",
}
# 구현 순서는 문서성 상수로 남긴다. 기능 동작에는 쓰이지 않지만,
# 이후 리팩터링 때 현재 우선순위가 무엇이었는지 테스트에서 확인할 수 있다.
ANSWER_IMPLEMENTATION_PRIORITIES = [
    "1. keep test_answer_agent.py passing",
    "2. add ticket-level exception handling and batch logging",
    "3. improve answer draft quality",
    "4. strengthen safety/factuality validation",
    "5. keep draft/evidence/safety persistence transactional",
    "6. verify API/frontend status consistency",
    "7. add Airflow operation logs and failure recovery policy",
]


class AnswerTarget(BaseModel):
    """qa_ticket과 최신 ticket_analysis를 합친 답변 생성 대상.

    필드는 실제 public schema의 qa_ticket/ticket_analysis 컬럼을 기준으로 둔다.
    extra=allow는 API/테스트에서 붙는 표시용 메타데이터를 깨지 않기 위한 호환 정책이다.
    """

    model_config = ConfigDict(extra="allow")

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


class RetrievalStrategy(BaseModel):
    """routing_target을 실행 가능한 근거 조회 옵션으로 정규화한다."""

    routing_target: str
    use_documents: bool = False
    use_operation_logs: bool = False
    fixed_answer: bool = False


class DraftContext(BaseModel):
    """LCEL 답변 초안 생성에 필요한 모든 입력.

    ticket/analysis는 AnswerTarget 계약을 공유해 기존 public helper와 LCEL 체인이
    같은 모델을 사용하게 한다.
    """

    ticket: AnswerTarget
    analysis: AnswerTarget
    evidence_docs: list[EvidenceItem] = Field(default_factory=list)
    regeneration_reason: str | None = None
    evidence_is_stale: bool = False


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


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


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


def _evaluate_context_safety(context: DraftContext) -> SafetyResult:
    """근거 존재 여부, 금칙 표현, 정책 단정 표현 기반으로 초안 안전성을 점검한다.

    LLM factuality는 현재 기본 경로에 붙이지 않는다. 외부 API 장애가 있어도
    답변 생성 배치가 안정적으로 돌아야 하므로, 규칙 기반 점수를 source of truth로 둔다.
    """

    draft_text = _compose_draft_text(context)
    thresholds = _safety_thresholds()
    has_evidence = bool(context.evidence_docs)

    toxicity = _term_match_score(draft_text, TOXIC_TERMS, per_match=0.6, maximum=1.0)
    policy = _term_match_score(draft_text, POLICY_RISK_TERMS, per_match=0.7, maximum=1.0)
    factuality = _factuality_score_from_evidence(context.evidence_docs)
    hallucination = round(max(0.0, min(1.0, 1.0 - factuality + (0.1 if policy > 0 else 0.0))), 4)

    action: SafetyAction = "ready_for_review"
    reason = "grounded_draft_ready_for_operator_review"
    if not has_evidence:
        action = "human_review"
        reason = "missing_evidence"
    elif context.evidence_is_stale:
        action = "human_review"
        reason = REGENERATION_EVIDENCE_POLICY["stale_evidence_reason"]
    elif toxicity >= thresholds["toxicity"] or policy >= thresholds["policy_violation"]:
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
    """분석 대상 1건을 초안과 safety 결과로 바꾸는 LCEL 체인."""

    return (
        RunnableLambda(AnswerTarget.model_validate)
        | RunnableLambda(_build_draft_context)
        | RunnableParallel(context=RunnablePassthrough(), draft_text=RunnableLambda(_generate_draft_text), safety=RunnableLambda(_evaluate_context_safety))
        | RunnableLambda(lambda parts: AnswerGenerationResult.model_validate(parts))
    )


def build_regeneration_chain():
    """기존 근거와 운영자 재생성 사유를 새 초안으로 바꾸는 LCEL 체인."""

    return RunnableLambda(_build_regeneration_context) | RunnableLambda(_result_from_context)


ANSWER_CHAIN = build_answer_generation_chain()
REGENERATION_CHAIN = build_regeneration_chain()


def run_answer_agent() -> dict[str, object]:
    """답변 초안이 없는 분석 완료 문의를 순차 처리하고 배치 결과를 기록한다.

    Airflow DAG 자체는 DB 접속 실패나 대상 조회 실패처럼 배치 시작 전 오류가 나면
    실패하도록 둔다. 반면 특정 티켓 1건의 retrieval/초안/safety 저장 실패는
    admin_event_logs에 남긴 뒤 다음 티켓 처리를 계속한다. 이렇게 해야 한 문의의
    비정상 데이터 때문에 전체 CS 자동화 답변 생성이 멈추지 않는다.
    """

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


def regenerate_agent(ticket_id: int | None = None, regeneration_reason: str | None = None) -> dict[str, object] | None:
    """운영자 재생성 사유를 기존 근거에 반영해 새 초안을 저장한다."""

    if ticket_id is None:
        return None
    limit = validate_regeneration_limit(ticket_id)
    if not limit["can_regenerate"]:
        return None

    context = fetch_regeneration_context(ticket_id)
    result = REGENERATION_CHAIN.invoke({"context": context, "regeneration_reason": regeneration_reason or ""})
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
    """문의 1건의 근거 조회, 초안 저장, safety 저장, 상태 갱신을 수행한다.

    LCEL 체인은 public 계약으로 유지하지만, 운영 관측성 때문에 실제 배치 처리에서는
    시작/검색/생성/저장 단계를 명시적으로 나눈다. 실패 로그에는 허용 metadata만
    들어가며 문의 원문이나 근거 전문은 저장하지 않는다.
    """

    target_model = AnswerTarget.model_validate(target)
    # 분석/대시보드는 chatbot/email 문의도 다룰 수 있지만, 답변 생성 agent는
    # 네이버 카페 게시글에 올릴 상담원 검토용 초안만 만든다. 배치 조회 조건을
    # 우회해 직접 호출되는 경우까지 막기 위한 마지막 방어선이다.
    if target_model.source_type != DEFAULT_ANSWER_SOURCE_TYPE:
        raise ValueError("answer_generation_supports_naver_cafe_only")
    strategy: dict[str, object] | None = None
    stage = "answer_generation"
    log_answer_generation_event(
        event_type=ANSWER_OBSERVABILITY_POLICY["events"]["start"],
        status="started",
        ticket_id=target_model.ticket_id,
        analysis_id=target_model.analysis_id,
    )
    try:
        stage = "retrieval"
        strategy = select_retrieval_strategy(target_model.model_dump())
        evidence = collect_answer_evidence(target_model.model_dump(), target_model.model_dump(), strategy)
        evidence_items = _standardize_evidence_items(evidence)
        context = DraftContext(ticket=target_model, analysis=target_model, evidence_docs=evidence_items)
        stage = "draft_generation"
        result = _result_from_context(context)
        stage = "persistence"
        persisted = persist_answer_generation_result(result, route_ticket=True)
        log_answer_generation_event(
            event_type=ANSWER_OBSERVABILITY_POLICY["events"]["success"],
            status="success",
            ticket_id=target_model.ticket_id,
            analysis_id=target_model.analysis_id,
            draft_id=persisted["draft"].get("draft_id") if isinstance(persisted.get("draft"), dict) else None,
            evidence_count=len(evidence_items),
            safety_action=result.safety.safety_action,
        )
    except Exception as exc:
        failure_reason = _classify_answer_failure(exc, stage, strategy)
        log_answer_generation_event(
            event_type=ANSWER_OBSERVABILITY_POLICY["events"]["failure"],
            status="failed",
            ticket_id=target_model.ticket_id,
            analysis_id=target_model.analysis_id,
            failure_reason=failure_reason,
        )
        raise


def persist_answer_generation_result(
    result: AnswerGenerationResult,
    *,
    route_ticket: bool,
) -> dict[str, object]:
    """초안, 근거, safety를 하나의 DB 트랜잭션으로 저장한다.

    psycopg connection context는 예외가 발생하면 rollback한다. 따라서 evidence 저장 중
    실패하거나 safety 저장 중 실패하면 앞서 insert한 answer_draft도 함께 롤백된다.
    route_ticket=True이면 같은 트랜잭션에서 qa_ticket.status까지 갱신해 저장 결과와
    상태 전이가 어긋나지 않게 한다.
    """

    ticket = result.context.ticket.model_dump()
    analysis = result.context.analysis.model_dump()
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _insert_answer_draft(cur, ticket, analysis, result.draft_text)
            evidence_docs = _insert_evidence_docs(
                cur,
                int(draft["draft_id"]),
                [item.model_dump() for item in result.context.evidence_docs],
            )
            safety = _insert_safety_results(
                cur,
                int(draft["draft_id"]),
                result.safety.model_dump(),
            )
            if route_ticket:
                _route_by_safety_result_with_cursor(cur, ticket, analysis, safety)
    return {"draft": draft, "evidence_docs": evidence_docs, "safety": safety}


def select_retrieval_strategy(analysis: dict[str, object]) -> dict[str, object]:
    """routing_target을 retrieval 옵션으로 정규화한다."""

    routing_target = str(analysis.get("routing_target") or "fixed_answer")
    options = RETRIEVAL_STRATEGY_BY_TARGET.get(routing_target, RETRIEVAL_STRATEGY_BY_TARGET["fixed_answer"])
    strategy = RetrievalStrategy(routing_target=routing_target, **options)
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
        evidence_docs=_standardize_evidence_items(evidence_docs),
        regeneration_reason=regeneration_reason,
    )
    return _generate_draft_text(context)


def _insert_answer_draft(cur: Any, ticket: dict[str, object], analysis: dict[str, object], draft_text: str) -> dict[str, object]:
    """answer_draft 실제 컬럼에 맞춰 초안을 insert한다.

    answer_draft 컬럼 계약:
    - draft_id: 직접 계산한 PK
    - ticket_id: qa_ticket FK
    - analysis_id: ticket_analysis FK, nullable
    - draft_text: 생성된 초안
    - created_at: CURRENT_TIMESTAMP
    """

    target = AnswerTarget.model_validate({**ticket, **analysis})
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
    next_status = _ticket_status_for_safety_action(action)
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
    limit = _regeneration_limit()
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
    return {
        "ticket": ticket,
        "analysis": analysis,
        "draft": draft,
        "evidence_docs": evidence_docs,
        "evidence_is_stale": _is_regeneration_evidence_stale(draft.get("created_at")) if draft else True,
        "evidence_max_age_days": _regeneration_evidence_max_age_days(),
    }


def log_regeneration_event(
    *,
    ticket_id: int,
    previous_draft_id: object,
    new_draft_id: object,
    regeneration_reason: str,
    retry_count: int,
    evidence_is_stale: bool,
) -> None:
    """재생성 완료 이벤트를 admin_event_logs에 남긴다.

    API 계층도 운영자 actor_admin_id와 함께 이벤트를 남기지만, agent가 단독으로
    실행되는 경우를 위해 agent 자체 이벤트도 기록한다. 원문/근거 전문은 남기지 않고
    추적에 필요한 식별자와 길이만 metadata에 저장한다.
    """

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
                    ticket_id,
                    "cs_auto_answer_agent",
                    "draft_regenerated",
                    "success",
                    Json(
                        {
                            "previous_draft_id": previous_draft_id,
                            "new_draft_id": new_draft_id,
                            "regeneration_reason_length": len(regeneration_reason),
                            "retry_count": retry_count,
                            "evidence_is_stale": evidence_is_stale,
                        }
                    ),
                ),
            )


def log_answer_ticket_failure(failure: dict[str, object]) -> None:
    """답변 생성 중 티켓 1건이 실패한 사실을 운영 로그에 남긴다.

    문의 원문, 답변 초안, 근거 전문은 로그에 남기지 않는다. 배치 장애 분석에
    필요한 ticket_id와 예외 종류/요약 메시지만 metadata로 저장한다.
    """

    ticket_id = failure.get("ticket_id")
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
                    ANSWER_BATCH_POLICY["ticket_failure_event"],
                    "failed",
                    Json(_log_metadata(ticket_id=ticket_id, failure_reason=failure.get("failure_reason"))),
                ),
            )


def log_answer_batch_event(batch_result: dict[str, object], status: str = "success") -> None:
    """답변 생성 배치 완료 이벤트를 admin_event_logs에 기록한다.

    Airflow task 로그는 실행 여부를 보여주지만, 운영 화면에서는 DB 이벤트 로그가
    기준이므로 target/processed/failed 건수 중심으로 저장한다. failures는 원문
    없이 ticket_id와 예외 요약만 최대 20건까지 보존한다.
    """

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_event_logs (
                    node_name,
                    event_type,
                    status,
                    metadata
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    "cs_auto_answer_agent",
                    ANSWER_BATCH_POLICY["completion_event"],
                    status,
                    Json(
                        {
                            "target_count": batch_result.get("target_count"),
                            "processed_count": batch_result.get("processed_count"),
                            "failed_count": batch_result.get("failed_count"),
                            "failures": [
                                _log_metadata(
                                    ticket_id=failure.get("ticket_id"),
                                    failure_reason=failure.get("failure_reason"),
                                )
                                for failure in list(batch_result.get("failures") or [])[:20]
                                if isinstance(failure, dict)
                            ],
                        }
                    ),
                ),
            )


def build_regeneration_prompt_context(context: dict[str, object], regeneration_reason: str) -> dict[str, object]:
    """기존 호출부 호환용 재생성 context builder."""

    return {
        "ticket": context.get("ticket") or {},
        "analysis": context.get("analysis") or {},
        "draft": context.get("draft") or {},
        "evidence_docs": context.get("evidence_docs") or [],
        "evidence_is_stale": bool(context.get("evidence_is_stale")),
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
