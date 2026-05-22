"""Node and router declarations for the operation LangGraph workflow."""

from __future__ import annotations

import logging
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal, cast

from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, ValidationError

from src.common.db.connection import db_connection
from src.common.llm.client import get_query_embedding, invoke_structured_llm

from .prompts import (
    ANALYSIS_PROMPT,
    ANSWER_PROMPT,
    HUMAN_REVIEW_PROMPT,
    QUERY_ROUTER_PROMPT,
    SAFETY_PROMPT,
    SYSTEM_PROMPT,
    URGENT_PROMPT,
    AnswerDraftResponse,
    HumanReviewResponse,
    QueryRoutingResponse,
    SafetyReviewResponse,
    TicketAnalysisResponse,
    UrgentDraftResponse,
    render_state,
)
from .state import (
    AnalysisResult,
    ApprovalRoute,
    EvidenceDocument,
    HumanDecision,
    HumanReviewResult,
    OperationState,
    QueryRoute,
    SafetyResult,
    TargetRoute,
    Ticket,
)


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[OperationState], StateUpdate]
# save_draft_node 이후 분기 4종: 근거 저장 → 승인 게이트, 긴급 알림, 사람 검수, 근거 부족 시 사람 검수
AfterDraftRoute = Literal["save_evidence_docs", "approval_gate", "urgent_alert", "human_review"]

# 답변 초안이 이 길이를 초과하면 오류를 기록한다 (고객 응답 가독성 상한선, 운영 정책)
_MAX_DRAFT_LENGTH = 3000

# 이 숫자 미만의 RAG 근거만 있으면 답변 신뢰도가 낮다고 판단해 human_review로 분기한다
# RAG 결과가 없거나 1개뿐이면 초안이 충분히 근거 기반이라고 볼 수 없기 때문
_MIN_EVIDENCE_COUNT = 2

# 워크플로우 실행 로그는 프로젝트 루트의 logs/operation/workflow.log 에 기록된다
# 배포 경로가 바뀌면 LOG_DIR 기준점인 parents[3] 인덱스를 함께 조정해야 한다
LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "operation"
LOG_FILE = LOG_DIR / "workflow.log"


class DbRow(BaseModel):
    """워크플로우 context에 저장하는 DB 행 모델입니다.

    `payments`, `documents` 등 여러 테이블 행을 JSON 직렬화 가능한 형태로 넘길 때 사용됩니다.
    """

    model_config = ConfigDict(extra="allow")


QUERY_ROUTES: tuple[QueryRoute, ...] = (
    "payment",
    "refund",
    "item_delivery",
    "gacha",
    "policy",
    "abuse",
    "outage",
)

TARGET_ROUTES: tuple[TargetRoute, ...] = ("rag_reply", "urgent_alert")

CONTEXT_NODE_BY_ROUTE: dict[QueryRoute, str] = {
    "payment": "payment_context_node",
    "refund": "refund_context_node",
    "item_delivery": "item_delivery_context_node",
    "gacha": "gacha_context_node",
    "policy": "policy_context_node",
    "abuse": "abuse_context_node",
    "outage": "outage_context_node",
}


def _operation_logger() -> logging.Logger:
    """운영 workflow 전용 파일 logger를 생성하거나 재사용합니다.

    모든 LangGraph 노드 실행 로그를 `logs/operation/workflow.log`로 연결합니다.
    """
    logger = logging.getLogger("operation.workflow")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def _state_log_fields(state: OperationState) -> dict[str, Any]:
    """로그에 남길 상태 식별자만 추려 민감 정보와 본문 과다 기록을 피합니다.

    `qa_ticket`, route, 저장 PK, status 중심으로 노드 실행 흐름을 추적하도록 연결합니다.
    """
    return {
        "ticket_id": state.ticket_id or state.ticket.ticket_id,
        "query_route": state.query_route,
        "target_route": state.target_route or state.analysis.target_route,
        "approval_route": state.approval_route,
        "human_decision": state.human_decision,
        "analysis_id": state.analysis_id,
        "draft_id": state.draft_id,
        "safety_id": state.safety_id,
        "response_id": state.response_id,
        "status": state.status,
    }


def _update_log_fields(update: StateUpdate) -> dict[str, Any]:
    """노드 반환값 중 추적에 필요한 키만 로그용 dict로 변환합니다.

    `analysis_id`, `draft_id`, route, status 같은 후속 노드 연결값을 중심으로 기록합니다.
    """
    if not update:
        return {}
    tracked_keys = {
        "query_route",
        "target_route",
        "approval_route",
        "human_decision",
        "analysis_id",
        "draft_id",
        "safety_id",
        "response_id",
        "notification_id",
        "status",
    }
    fields = {key: update[key] for key in tracked_keys if key in update}
    if "final_answer" in update:
        fields["final_answer_present"] = bool(update["final_answer"])
    return fields


def _with_node_logging(node_name: str, handler: NodeHandler) -> NodeHandler:
    """LangGraph 노드 실행 전후를 파일 로그로 감싸는 wrapper를 만듭니다.

    `NODE_FUNCTIONS`에 연결되어 모든 workflow 실행에서 시작, 성공, 실패와 소요 시간을 기록합니다.
    """

    @wraps(handler)
    def wrapped(state: OperationState) -> StateUpdate:
        logger = _operation_logger()
        current = _state(state)
        started_at = perf_counter()
        logger.info("node_start name=%s state=%s", node_name, _state_log_fields(current))
        try:
            update = handler(current)
        except Exception:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception("node_error name=%s elapsed_ms=%s state=%s", node_name, elapsed_ms, _state_log_fields(current))
            raise

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info("node_end name=%s elapsed_ms=%s update=%s", node_name, elapsed_ms, _update_log_fields(update))
        return update

    return wrapped


def _state(state: OperationState | dict[str, Any]) -> OperationState:
    """LangGraph가 넘긴 상태를 `OperationState`로 정규화합니다.

    모든 노드 함수와 라우터가 같은 Pydantic 상태 계약을 사용하도록 연결합니다.
    """
    return OperationState.model_validate(state)


def _dump_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DB 조회 행 목록을 JSON 안전한 dict 목록으로 변환합니다.

    context 노드들이 조회한 `payments`, `refunds`, `documents` 행을 LLM 프롬프트에 연결합니다.
    """
    return [DbRow.model_validate(row).model_dump(mode="json") for row in rows]


def _rrf_merge(
    keyword_rows: dict[str, dict[str, Any]],
    vector_rows: dict[str, dict[str, Any]],
    *,
    top_k: int = 8,   # BM25·vector 각 10건 → RRF 후 LLM 컨텍스트 토큰 한도 고려해 8건으로 축소
    k: int = 60,      # Cormack et al. 2009 RRF 논문 표준값: 순위 충격(rank shock) 완화에 효과적
) -> list[dict[str, Any]]:
    """BM25 키워드 결과와 pgvector 결과를 Reciprocal Rank Fusion으로 병합합니다.

    descriptions.md `idx_documents_embeddings_vector_cosine` IVFFlat 인덱스 기반 결과를
    BM25 ts_rank_cd 결과와 합쳐 hybrid retrieval 점수를 만듭니다.
    score 내림차순으로 keyword_rows → vector_rows 순으로 rank를 계산합니다.
    """
    keyword_ranks = {
        cid: rank
        for rank, cid in enumerate(
            sorted(keyword_rows, key=lambda x: -(keyword_rows[x].get("score") or 0.0)), start=1
        )
    }
    vector_ranks = {
        cid: rank
        for rank, cid in enumerate(
            sorted(vector_rows, key=lambda x: -(vector_rows[x].get("score") or 0.0)), start=1
        )
    }
    all_ids = set(keyword_rows) | set(vector_rows)
    scored: list[tuple[float, dict[str, Any]]] = []
    for cid in all_ids:
        rrf_score = 0.0
        if cid in keyword_ranks:
            rrf_score += 1.0 / (k + keyword_ranks[cid])
        if cid in vector_ranks:
            rrf_score += 1.0 / (k + vector_ranks[cid])
        row = keyword_rows.get(cid) or vector_rows[cid]
        scored.append((rrf_score, row))
    scored.sort(key=lambda x: -x[0])
    return [row for _, row in scored[:top_k]]


def _ticket_key(state: OperationState) -> str:
    """현재 상태에서 DB 저장과 조회에 사용할 티켓 ID를 확정합니다.

    `qa_ticket`을 기준으로 `ticket_analysis`, `answer_draft`, `final_response` FK를 연결합니다.
    """
    ticket_id = state.ticket_id or state.ticket.ticket_id
    if not ticket_id:
        raise ValueError("operation workflow requires ticket_id")
    return str(ticket_id)



def _query_text(state: OperationState) -> str:
    """검색과 LLM 입력에 사용할 문의 텍스트를 확정합니다.

    `qa_ticket.raw_query`가 없을 때 제목을 보조로 쓰며, RAG 검색 노드와 분석 노드에 연결됩니다.
    """
    query_text = state.query_text or state.ticket.body or state.ticket.title
    if not query_text:
        raise ValueError("operation workflow requires query_text or ticket body")
    return query_text


def _fetch_ticket(ticket_id: str) -> dict[str, Any]:
    """`qa_ticket`에서 티켓과 사용자/계정 정보를 함께 조회합니다.

    `community_users`, `game_accounts`를 LEFT JOIN하여 이후 context 노드가 FK 기준을 사용할 수 있게 합니다.
    """
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.user_id,
                    t.account_id,
                    t.title,
                    t.raw_query,
                    t.source_type,
                    t.responder_type,
                    t.status,
                    t.inquiry_created_at,
                    t.session_id,
                    u.email,
                    u.nickname,
                    u.user_status,
                    a.game_name,
                    a.uid,
                    a.server_region,
                    a.progression_level,
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"qa_ticket not found: {ticket_id}")
            return dict(row)


def _payment_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    # game_accounts를 경유해 user_id 또는 account_id 기준으로 결제 이력을 조회한다
    # payments에는 user_id 컬럼이 없으므로 game_accounts를 반드시 JOIN해야 한다
    # LIMIT 10: LLM 프롬프트 토큰 한도 내 최신 이력만 제공하기 위한 상한 (모든 route 공통)
    cur.execute(
        """
        SELECT p.*
        FROM payments p
        JOIN game_accounts a ON a.account_id = p.account_id
        WHERE a.user_id = %s OR p.account_id = %s
        ORDER BY p.paid_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _refund_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    # refunds에는 account_id가 없어 payments → game_accounts 체인으로 사용자를 확인해야 한다
    # p.product_name, p.payment_status 등 원결제 정보를 함께 조회해 환불 심사 근거를 제공한다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT r.*, p.account_id, p.product_name, p.payment_status, p.paid_at
        FROM refunds r
        JOIN payments p ON p.payment_id = r.payment_id
        JOIN game_accounts a ON a.account_id = p.account_id
        WHERE a.user_id = %s OR p.account_id = %s
        ORDER BY r.requested_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _item_delivery_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    # item_delivery_logs.account_id → game_accounts.account_id → user_id 로 사용자를 필터링한다
    # expected_at이 NULL이면 delivered_at 기준으로 정렬해 최신 지급 상태를 먼저 보여준다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT d.*
        FROM item_delivery_logs d
        JOIN game_accounts a ON a.account_id = d.account_id
        WHERE a.user_id = %s OR d.account_id = %s
        ORDER BY d.expected_at DESC NULLS LAST, d.delivered_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _gacha_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    # gacha_logs는 account_id를 직접 보유한다 — game_accounts JOIN은 user_id 필터 목적
    # pulled_at 역순으로 최근 뽑기 이력을 보여줘 pity count 흐름을 확인할 수 있게 한다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT g.*
        FROM gacha_logs g
        JOIN game_accounts a ON a.account_id = g.account_id
        WHERE a.user_id = %s OR g.account_id = %s
        ORDER BY g.pulled_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _abuse_rows(cur: Any, *, user_id: Any, account_id: Any, ticket_id: str) -> list[dict[str, Any]]:
    # insight는 user_id/account_id/ticket_id 세 기준을 모두 보유한다
    # voc_feedback은 LEFT JOIN: 해당 티켓에 VOC가 없어도 insight 행은 반환해야 한다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT i.*, v.voc_type, v.sentiment AS voc_sentiment, v.topic_keywords
        FROM insight i
        LEFT JOIN voc_feedback v ON v.ticket_id = i.ticket_id
        WHERE i.user_id = %s OR i.ticket_id = %s OR i.account_id = %s
        ORDER BY i.inquiry_created_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, ticket_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _outage_rows(cur: Any, **_: Any) -> list[dict[str, Any]]:
    # outage 관련 공지는 FK가 없으므로 category/title/raw_content ILIKE로 전문 검색한다
    # 가장 최근 업데이트된 장애 공지를 우선 반환해 운영자가 최신 상황을 파악하게 한다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT documents_id, source_type, category, title, raw_content, source_url, published_at, updated_at
        FROM documents
        WHERE category ILIKE %s OR title ILIKE %s OR raw_content ILIKE %s
        ORDER BY updated_at DESC NULLS LAST, published_at DESC NULLS LAST
        LIMIT 10
        """,
        ("%outage%", "%outage%", "%outage%"),
    )
    return [dict(row) for row in cur.fetchall()]


def _policy_rows(cur: Any, **_: Any) -> list[dict[str, Any]]:
    # policy 및 기타 route: 정책/가이드/약관 문서를 ILIKE로 검색한다
    # documents 테이블 category에 "policy" 가 포함된 문서를 우선 반환한다
    # LIMIT 10: _payment_rows 주석 참조 (모든 route 공통 상한)
    cur.execute(
        """
        SELECT documents_id, source_type, category, title, raw_content, source_url, published_at, updated_at
        FROM documents
        WHERE category ILIKE %s OR title ILIKE %s OR raw_content ILIKE %s
        ORDER BY updated_at DESC NULLS LAST, published_at DESC NULLS LAST
        LIMIT 10
        """,
        ("%policy%", "%policy%", "%policy%"),
    )
    return [dict(row) for row in cur.fetchall()]


# workflow.md §3 노드별 책임 기반 route → 쿼리 함수 매핑
# if/elif 체인 대신 dict 디스패치를 사용해 route 추가 시 이 dict만 수정하면 된다
_ROUTE_QUERY_FN: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "payment": _payment_rows,
    "refund": _refund_rows,
    "item_delivery": _item_delivery_rows,
    "gacha": _gacha_rows,
    "abuse": _abuse_rows,
    "outage": _outage_rows,
    "policy": _policy_rows,
}


def _context_for_route(route: QueryRoute, state: OperationState) -> list[dict[str, Any]]:
    """라우팅 결과에 맞춰 티켓 주변 업무 데이터를 조회합니다.

    `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight`, `documents`를 노드별 context로 연결합니다.
    """
    ticket_id = _ticket_key(state)
    user_id = state.ticket.user_id or state.ticket.metadata.get("user_id")
    account_id = state.ticket.metadata.get("account_id")
    query_fn = _ROUTE_QUERY_FN.get(route, _policy_rows)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return query_fn(cur, user_id=user_id, account_id=account_id, ticket_id=ticket_id)

def _add_context(state: OperationState, route: QueryRoute) -> StateUpdate:
    """조회한 route별 업무 context를 workflow state에 병합합니다.

    query router가 선택한 route와 실제 context node 이름을 `context_nodes`에 함께 기록합니다.
    """
    rows = _dump_rows(_context_for_route(route, state))
    context = state.context | {route: rows}
    return {"context": context, "context_nodes": [*state.context_nodes, CONTEXT_NODE_BY_ROUTE[route]]}

def load_ticket(state: OperationState) -> StateUpdate:
    """워크플로우 시작 시 `qa_ticket` 기준으로 문의 원문을 로드합니다.

    `community_users`, `game_accounts`와 연결된 메타데이터를 `Ticket.metadata`에 담아 뒤 노드에 전달합니다.
    """
    current = state
    if current.ticket_id:
        row = _fetch_ticket(current.ticket_id)
        ticket = Ticket(
            ticket_id=str(row.get("ticket_id")),
            user_id=str(row.get("user_id")),
            title=row.get("title"),
            body=row.get("raw_query"),
            channel=row.get("source_type"),
            responder_type=row.get("responder_type"),
            created_at=str(row.get("inquiry_created_at")) if row.get("inquiry_created_at") else None,
            metadata=row,
        )
        return {"ticket": ticket, "query_text": ticket.body, "status": row.get("status")}
    query_text = _query_text(current)
    return {"query_text": query_text}


def query_router(state: OperationState) -> StateUpdate:
    """문의 내용을 LLM으로 분류해 업무 route를 결정합니다.

    결과는 `payment_context_node` 등 route별 context 노드와 연결됩니다.
    LLM이 허용값 외 route를 반환하거나 스키마 검증 실패 시 "policy"로 fallback합니다.
    재시도 흐름에서는 metadata.retry_reason을 프롬프트에 명시적으로 주입합니다.
    """
    current = state
    user_prompt = QUERY_ROUTER_PROMPT.format(state_json=render_state(current))
    retry_reason = current.metadata.get("retry_reason")
    if retry_reason:
        user_prompt += f"\n\n[RETRY CONTEXT] Previous draft was rejected. Rejection reason: {retry_reason}"
    try:
        response = invoke_structured_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=QueryRoutingResponse,
        )
        query_route: QueryRoute = response.query_route if response.query_route in QUERY_ROUTES else "policy"
        route_reason = response.route_reason
    except ValidationError:
        query_route = "policy"
        route_reason = "fallback: LLM returned invalid query_route"
    return {"query_route": query_route, "query_route_reason": route_reason}


def payment_context_node(state: OperationState) -> StateUpdate:
    """결제 문의에 필요한 최근 결제 내역을 context에 추가합니다.

    `payments`와 `game_accounts`를 기준으로 해당 사용자/계정의 결제 데이터를 연결합니다.
    """
    return _add_context(state, "payment")


def refund_context_node(state: OperationState) -> StateUpdate:
    """환불 문의에 필요한 환불 및 원결제 내역을 context에 추가합니다.

    `refunds`, `payments`, `game_accounts`를 연결해 환불 상태와 결제 상태를 함께 제공합니다.
    """
    return _add_context(state, "refund")


def item_delivery_context_node(state: OperationState) -> StateUpdate:
    """아이템 미지급 문의에 필요한 지급 로그를 context에 추가합니다.

    `item_delivery_logs`와 `game_accounts`를 연결해 지급 예정/완료 상태를 확인합니다.
    """
    return _add_context(state, "item_delivery")


def gacha_context_node(state: OperationState) -> StateUpdate:
    """가챠 문의에 필요한 뽑기 이력을 context에 추가합니다.

    `gacha_logs`와 `game_accounts`를 연결해 배너, 아이템, pity count 정보를 제공합니다.
    """
    return _add_context(state, "gacha")


def policy_context_node(state: OperationState) -> StateUpdate:
    """정책/가이드 문의에 필요한 문서 context를 추가합니다.

    `documents`의 policy 관련 문서를 조회해 이후 RAG 답변과 분석 노드에 연결합니다.
    """
    return _add_context(state, "policy")


def abuse_context_node(state: OperationState) -> StateUpdate:
    """어뷰징/위험 문의에 필요한 인사이트와 VOC context를 추가합니다.

    `insight`, `voc_feedback`을 `qa_ticket`, `community_users`, `game_accounts` 기준으로 연결합니다.
    """
    return _add_context(state, "abuse")


def outage_context_node(state: OperationState) -> StateUpdate:
    """장애/접속 실패 문의에 필요한 공지 문서 context를 추가합니다.

    `documents`의 outage 관련 문서를 조회해 긴급 대응 여부 판단과 연결합니다.
    """
    return _add_context(state, "outage")


def analyze_ticket(state: OperationState) -> StateUpdate:
    """티켓과 DB context를 기반으로 위험도와 목표 route를 분석합니다.

    분석 결과는 `ticket_analysis` 저장과 `rag_retrieve_node` 또는 `urgent_draft_node` 분기로 연결됩니다.
    LLM이 허용값 외 target_route를 반환하거나 스키마 검증 실패 시 "rag_reply"로 fallback합니다.
    재시도 흐름에서는 metadata.retry_reason을 프롬프트에 명시적으로 주입합니다.
    """
    current = state
    user_prompt = ANALYSIS_PROMPT.format(state_json=render_state(current))
    retry_reason = current.metadata.get("retry_reason")
    if retry_reason:
        user_prompt += f"\n\n[RETRY CONTEXT] Previous draft was rejected. Rejection reason: {retry_reason}"
    try:
        response = invoke_structured_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=TicketAnalysisResponse,
        )
        target_route: TargetRoute = response.target_route if response.target_route in TARGET_ROUTES else "rag_reply"
        analysis = AnalysisResult(
            query_route=response.query_route,
            target_route=target_route,
            risk_level=response.risk_level,
            risk_reason=response.risk_reason,
            summary=response.summary,
            required_actions=response.required_actions,
        )
        return {"analysis": analysis, "query_route": response.query_route, "target_route": target_route}
    except ValidationError:
        fallback_target: TargetRoute = "rag_reply"
        analysis = AnalysisResult(
            query_route=current.query_route,
            target_route=fallback_target,
        )
        return {"analysis": analysis, "target_route": fallback_target}


def save_analysis(state: OperationState) -> StateUpdate:
    """LLM 분석 결과를 `ticket_analysis` 테이블에 저장합니다.

    `qa_ticket.ticket_id`를 FK로 사용하며 이후 `answer_draft.analysis_id`와 연결됩니다.
    DB INSERT 실패 시 예외를 삼키지 않고 state.errors에 기록한 뒤 반환합니다.
    """
    current = state
    ticket_id = _ticket_key(current)
    query_text = _query_text(current)
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ticket_analysis (
                        ticket_id, category, responder_type, enriched_query,
                        risk_level, sentiment, routing_target, summary, analyzed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING analysis_id
                    """,
                    (
                        ticket_id,
                        current.analysis.query_route,
                        current.ticket.responder_type or current.target_route,
                        query_text,
                        current.analysis.risk_level,
                        # sentiment: TicketAnalysisResponse에 해당 필드가 정의되어 있지 않아 None으로 고정한다
                        # 추후 LLM 응답 스키마에 sentiment를 추가하면 current.analysis.sentiment 를 사용하면 된다
                        None,
                        current.analysis.target_route,
                        current.analysis.summary,
                    ),
                )
                analysis_id = cur.fetchone()[0]
        return {"analysis_id": analysis_id}
    except Exception as exc:
        error_msg = f"save_analysis DB error (ticket_id={ticket_id}): {exc}"
        return {"errors": [*current.errors, error_msg]}


def rag_retrieve_node(state: OperationState) -> StateUpdate:
    """문의 텍스트로 문서 청크를 검색해 답변 근거를 구성합니다.

    BM25 키워드 검색과 pgvector 코사인 유사도 검색을 RRF로 병합하는 hybrid retrieval을 수행합니다.
    `descriptions.md` IVFFlat cosine 인덱스(`idx_documents_embeddings_vector_cosine`)를 활용하며,
    임베딩 생성 실패 시 BM25 단독 검색으로 fallback합니다.
    """
    current = state
    query_text = _query_text(current)

    query_embedding = get_query_embedding(query_text)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # BM25 keyword search
            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.document_id,
                    d.source_type,
                    d.category,
                    d.title,
                    c.chunk_text,
                    ts_rank_cd(to_tsvector('simple', c.chunk_text), plainto_tsquery('simple', %s)) AS score
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                WHERE to_tsvector('simple', c.chunk_text) @@ plainto_tsquery('simple', %s)
                   OR c.chunk_text ILIKE %s
                   OR d.title ILIKE %s
                ORDER BY score DESC NULLS LAST, c.created_at DESC NULLS LAST
                LIMIT 10
                """,
                (query_text, query_text, f"%{query_text}%", f"%{query_text}%"),
            )
            keyword_rows: dict[str, dict[str, Any]] = {
                row["chunk_id"]: dict(row) for row in cur.fetchall()
            }

            # pgvector cosine similarity search (IVFFlat index)
            vector_rows: dict[str, dict[str, Any]] = {}
            if query_embedding:
                embedding_literal = "[" + ",".join(f"{v:.8f}" for v in query_embedding) + "]"
                cur.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.document_id,
                        d.source_type,
                        d.category,
                        d.title,
                        c.chunk_text,
                        1.0 - (e.embedding_vector <=> %s::vector) AS score
                    FROM documents_embeddings e
                    JOIN documents_chunks c ON c.chunk_id = e.chunk_id
                    JOIN documents d ON d.documents_id = c.document_id
                    ORDER BY e.embedding_vector <=> %s::vector
                    LIMIT 10
                    """,
                    (embedding_literal, embedding_literal),
                )
                vector_rows = {row["chunk_id"]: dict(row) for row in cur.fetchall()}

    merged = _rrf_merge(keyword_rows, vector_rows, top_k=8)
    docs = [
        EvidenceDocument(
            doc_id=row.get("chunk_id"),
            source=row.get("source_type"),
            title=row.get("title"),
            content=row.get("chunk_text"),
            score=float(row.get("score") or 0),
            metadata=row,
        )
        for row in merged
    ]
    return {"retrieved_docs": docs, "evidence_doc_ids": [doc.doc_id for doc in docs if doc.doc_id]}


def generate_answer_node(state: OperationState) -> StateUpdate:
    """검색 근거와 업무 context를 바탕으로 고객 답변 초안을 생성합니다.

    생성된 문안은 `answer_draft` 저장 노드와 연결되고, 근거 ID는 `evidence_docs`와 연결됩니다.

    검증 (todolist.md P1):
    - evidence_doc_ids: rag_retrieve_node가 반환한 실제 ID 집합에 없는 값을 제거합니다.
    - 빈 초안: strip 후 비어 있으면 state.errors에 기록하고 answer_draft를 None으로 설정합니다.
    - 과도한 길이: _MAX_DRAFT_LENGTH 초과 시 state.errors에 기록합니다 (초안은 유지).
    """
    current = state
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=ANSWER_PROMPT.format(state_json=render_state(current)),
        response_model=AnswerDraftResponse,
    )

    # evidence_doc_ids 유효성 필터링: RAG 검색 결과에 없는 ID 제거
    valid_ids: set[str] = set(current.evidence_doc_ids)
    filtered_ids = [doc_id for doc_id in response.evidence_doc_ids if doc_id in valid_ids]

    answer_draft: str | None = response.answer_draft
    errors = list(current.errors)

    # 빈 초안 검증
    if not answer_draft or not answer_draft.strip():
        errors.append("generate_answer_node: LLM returned empty answer_draft")
        answer_draft = None
    # 과도한 길이 검증 (_MAX_DRAFT_LENGTH 초과)
    elif len(answer_draft) > _MAX_DRAFT_LENGTH:
        errors.append(
            f"generate_answer_node: answer_draft too long"
            f" ({len(answer_draft)} chars > {_MAX_DRAFT_LENGTH})"
        )

    return {"answer_draft": answer_draft, "evidence_doc_ids": filtered_ids, "errors": errors}


def urgent_draft_node(state: OperationState) -> StateUpdate:
    """긴급 운영 확인이 필요한 티켓의 운영자 알림 초안을 생성합니다.

    `urgent_alert_node`가 사용할 메시지를 만들며 `notification_logs` 저장 흐름과 연결됩니다.
    LLM이 빈 urgent_draft를 반환하면 state.errors에 기록하고 None을 설정합니다.
    """
    current = state
    try:
        response = invoke_structured_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=URGENT_PROMPT.format(state_json=render_state(current)),
            response_model=UrgentDraftResponse,
        )
        urgent_draft: str | None = response.urgent_draft
    except ValidationError:
        urgent_draft = None

    errors = list(current.errors)
    if not urgent_draft or not urgent_draft.strip():
        errors.append("urgent_draft_node: LLM returned empty urgent_draft")
        urgent_draft = None

    return {"urgent_draft": urgent_draft, "answer_draft": urgent_draft, "errors": errors}


def save_draft_node(state: OperationState) -> StateUpdate:
    """생성된 고객 답변 또는 긴급 초안을 `answer_draft`에 저장합니다.

    `ticket_analysis.analysis_id`와 `qa_ticket.ticket_id`를 FK로 연결해 검수/최종응답의 기준 초안을 만듭니다.
    analysis_id 누락(save_analysis 실패)이나 DB FK 위반 시 state.errors에 기록하고 반환합니다.
    """
    current = state
    # analysis_id 누락: FK 위반 전 사전 차단 (수동 개입 필요 실패로 분류)
    if current.analysis_id is None:
        return {"errors": [*current.errors, "save_draft_node: analysis_id is required (save_analysis may have failed)"]}
    ticket_id = _ticket_key(current)
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO answer_draft (
                        ticket_id, analysis_id, draft_text, prompt_version, created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING draft_id
                    """,
                    (
                        ticket_id,
                        current.analysis_id,
                        current.answer_draft or current.urgent_draft,
                        # prompt_version: 이 워크플로우 버전 식별자, DB에 기록해 답변 생성 버전을 추적한다
                        # 프롬프트 개정 시 이 값을 바꿔 이전 버전 초안과 구분할 수 있다
                        # 변경 절차: prompts.py 수정 → 이 값을 새 버전명으로 갱신 → 함께 커밋
                        "operation-workflow",
                    ),
                )
                draft_id = cur.fetchone()[0]
        return {"draft_id": draft_id}
    except Exception as exc:
        error_msg = f"save_draft_node DB error (ticket_id={ticket_id}, analysis_id={current.analysis_id}): {exc}"
        return {"errors": [*current.errors, error_msg]}


def save_evidence_docs_node(state: OperationState) -> StateUpdate:
    """LLM이 인용한 근거 문서만 `evidence_docs` 테이블에 저장합니다.

    각 근거는 `answer_draft.draft_id`에 연결되어 안전성 검수와 사후 추적에 사용됩니다.
    generate_answer_node가 필터링한 evidence_doc_ids 기준으로만 저장해
    LLM이 실제 인용하지 않은 검색 결과는 제외합니다.
    """
    current = state
    if current.draft_id is None:
        return {"errors": [*current.errors, "save_evidence_docs_node: draft_id is required"]}

    # generate_answer_node가 LLM 인용 기준으로 필터링한 ID 집합
    cited_ids: set[str] = set(current.evidence_doc_ids)
    cited_docs = [doc for doc in current.retrieved_docs if doc.doc_id in cited_ids]

    if not cited_docs:
        return {
            "status": "evidence_empty",
            "errors": [*current.errors, "save_evidence_docs_node: no cited evidence docs to save"],
        }

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                for rank, document in enumerate(cited_docs, start=1):
                    cur.execute(
                        """
                        INSERT INTO evidence_docs (
                            draft_id, source_type, source_id,
                            evidence_text, relevance_score, retrieval_rank
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING evidence_id
                        """,
                        (
                            current.draft_id,
                            document.source,
                            document.doc_id,
                            document.content,
                            document.score,
                            rank,
                        ),
                    )
        return {"status": "evidence_saved"}
    except Exception as exc:
        error_msg = f"save_evidence_docs_node DB error (draft_id={current.draft_id}): {exc}"
        return {"status": "evidence_error", "errors": [*current.errors, error_msg]}


def approval_gate_node(state: OperationState) -> StateUpdate:
    """답변 초안을 안전성/근거성 기준으로 검수합니다.

    결과는 `safety_results` 저장 후 승인, 사람 검수, 긴급 알림 route와 연결됩니다.
    """
    current = state
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=SAFETY_PROMPT.format(state_json=render_state(current)),
        response_model=SafetyReviewResponse,
    )
    safety = SafetyResult(
        approved=response.approved,
        evidence_matched=response.evidence_matched,
        hallucination_detected=response.hallucination_detected,
        policy_violation_detected=response.policy_violation_detected,
        unsafe_expression_detected=response.unsafe_expression_detected,
        reasons=response.reasons,
    )
    # 우선순위: 정책 위반 또는 critical 위험도 → 즉시 긴급 알림 (운영자가 직접 처리해야 하는 케이스)
    # approved=True라도 policy_violation이면 긴급 처리가 우선이다
    # hallucination / unsafe_expression만 있으면 사람 검수로 넘겨 수정 기회를 준다
    if response.policy_violation_detected or current.analysis.risk_level == "critical":
        approval_route: ApprovalRoute = "urgent_alert"
    elif response.approved:
        approval_route = "approved"
    else:
        approval_route = "human_review"
    return {"safety_result": safety, "approval_route": approval_route}


def save_safety_result_node(state: OperationState) -> StateUpdate:
    """승인 게이트의 검수 결과를 `safety_results`에 저장합니다.

    `answer_draft.draft_id`와 연결되어 최종 응답 또는 운영자 검토의 판단 근거가 됩니다.
    """
    current = state
    if current.draft_id is None:
        raise ValueError("safety_results requires draft_id")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO safety_results (
                    draft_id, hallucination_score, toxicity_score,
                    policy_violation_score, factuality_score, checked_at,
                    safety_action, safety_reason, retry_count
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING safety_id
                """,
                (
                    current.draft_id,
                    1.0 if current.safety_result.hallucination_detected else 0.0,
                    1.0 if current.safety_result.unsafe_expression_detected else 0.0,
                    1.0 if current.safety_result.policy_violation_detected else 0.0,
                    1.0 if current.safety_result.evidence_matched else 0.0,
                    current.approval_route,
                    "\n".join(current.safety_result.reasons),
                    current.retry_count or 0,
                ),
            )
            safety_id = cur.fetchone()[0]
    return {"safety_id": safety_id}


def publish_final_answer_node(state: OperationState) -> StateUpdate:
    """승인된 최종 답변을 `final_response`에 저장하고 티켓을 종료합니다.

    `qa_ticket.status`를 `closed`로 갱신하며 고객 응답 이력과 원 티켓을 연결합니다.
    """
    current = state
    final_answer = current.edited_answer or current.answer_draft or current.urgent_draft
    if not final_answer:
        raise ValueError("final_response requires final answer text")
    ticket_id = _ticket_key(current)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO final_response (
                    ticket_id, draft_id, final_text, safety_action, created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id
                """,
                (
                    ticket_id,
                    current.draft_id,
                    final_answer,
                    current.approval_route,
                ),
            )
            response_id = cast(int, cur.fetchone()[0])
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("closed", ticket_id),
            )
    return {"final_answer": final_answer, "response_id": response_id, "status": "closed"}


def human_review_node(state: OperationState) -> StateUpdate:
    """사람 검수 단계에서 필요한 결정 초안을 LLM으로 정리합니다.

    승인, 반려, 편집 결정은 `publish_final_answer_node`, `retry_routing_node`, `edit_answer_node`와 연결됩니다.
    """
    current = state
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=HUMAN_REVIEW_PROMPT.format(state_json=render_state(current)),
        response_model=HumanReviewResponse,
    )
    human_review = HumanReviewResult(
        decision=response.decision,
        reason=response.reason,
        edited_answer=response.edited_answer,
    )
    return {
        "human_decision": human_review.decision,
        "human_review": human_review,
        "edited_answer": human_review.edited_answer,
    }


def retry_routing_node(state: OperationState) -> StateUpdate:
    """사람 검수에서 반려된 건을 재라우팅할 수 있도록 상태를 초기화합니다.

    기존 초안/검수 route를 지우고 `query_router`로 되돌려 재분류 흐름과 연결합니다.
    max_retries 초과 시 urgent_alert 로 분기하기 위해 approval_route를 설정합니다.
    """
    current = state
    retry_count = (current.retry_count or 0) + 1
    max_retries = current.max_retries if current.max_retries is not None else 3
    update: dict = {
        "retry_count": retry_count,
        "answer_draft": None,
        "urgent_draft": None,
        "approval_route": None,
        "human_decision": None,
        "metadata": current.metadata | {"retry_reason": current.human_review.reason},
    }
    if retry_count >= max_retries:
        update["approval_route"] = "urgent_alert"
    return update


def edit_answer_node(state: OperationState) -> StateUpdate:
    """사람 검수에서 수정된 답변을 최종 답변 후보로 반영합니다.

    `human_review.edited_answer`를 `save_final_edit_node`와 최종 발행 노드에 연결합니다.
    """
    current = state
    return {"edited_answer": current.human_review.edited_answer}


def save_final_edit_node(state: OperationState) -> StateUpdate:
    """human_review의 edit 결정 후 수정 답변을 최종 답변으로 확정합니다.

    workflow.md §3 및 langgraph.mmd 에 명시된 edit 경로 전용 노드입니다.
    현재는 DB write 없이 상태만 업데이트하며, 실제 DB 저장은
    다음 단계인 publish_final_answer_node가 final_response 테이블에 기록합니다.
    todolist.md P3: 이름 변경 또는 수정 이력 별도 테이블 저장은 향후 개선 사항입니다.
    """
    current = state
    # edited_answer가 없으면 edit 경로 진입 자체가 잘못된 것이므로 오류를 기록하고 반환한다
    if not current.edited_answer:
        return {
            "errors": [
                *current.errors,
                "save_final_edit_node: edited_answer is required (edit path only)",
            ]
        }
    # final_answer를 설정해 publish_final_answer_node가 edited_answer를 최우선으로 사용하게 한다
    return {"final_answer": current.edited_answer}


def urgent_alert_node(state: OperationState) -> StateUpdate:
    """긴급 알림 메시지를 `notification_logs`에 저장하고 `qa_ticket.status`를 갱신합니다.

    `qa_ticket.ticket_id`와 운영 채널을 연결해 담당자 확인 대기 상태를 남깁니다.
    workflow.md §3: 출력 책임에 qa_ticket.status=urgent_alert_pending DB 반영이 포함됩니다.
    """
    current = state
    ticket_id = _ticket_key(current)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_logs (
                    ticket_id, channel, status, message, sent_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING notification_id
                """,
                (
                    ticket_id,
                    # "operation": notification_logs.channel 운영 내부 채널 식별자 (workflow.md §3 urgent_alert_node 출력 기준)
                    "operation",
                    "pending",
                    current.urgent_draft or current.answer_draft,
                ),
            )
            notification_id = cast(int, cur.fetchone()[0])
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("urgent_alert_pending", ticket_id),
            )
    return {"notification_id": notification_id, "status": "urgent_alert_pending"}


def route_by_query(state: OperationState) -> QueryRoute:
    """query router 결과를 context 노드 이름으로 변환할 route 값을 반환합니다.

    `CONTEXT_NODE_BY_ROUTE`와 연결되어 결제, 환불, 정책 등 업무별 조회 노드를 선택합니다.
    허용값(QUERY_ROUTES) 외 값이 있으면 명시적 ValueError를 발생시킵니다.
    """
    current = _state(state)
    if current.query_route is None:
        raise ValueError("query_route is required for routing")
    if current.query_route not in QUERY_ROUTES:
        raise ValueError(f"query_route has unexpected value: {current.query_route!r}")
    return current.query_route


def route_by_target(state: OperationState) -> TargetRoute:
    """분석 결과의 목표 route를 반환해 답변 생성 방향을 선택합니다.

    `TARGET_ROUTE_TARGETS`와 연결되어 RAG 답변 또는 긴급 알림 초안 흐름으로 분기합니다.
    허용값(TARGET_ROUTES) 외 값이 있으면 명시적 ValueError를 발생시킵니다.
    """
    current = _state(state)
    resolved = current.target_route or current.analysis.target_route
    if resolved is None:
        raise ValueError("target_route is required for routing")
    if resolved not in TARGET_ROUTES:
        raise ValueError(f"target_route has unexpected value: {resolved!r}")
    return cast(TargetRoute, resolved)


def route_after_save_draft(state: OperationState) -> AfterDraftRoute:
    """초안 저장 후 근거 문서 저장이 필요한지 결정합니다.

    검색 근거가 _MIN_EVIDENCE_COUNT 이상이면 evidence_docs 저장으로,
    미충족 시 답변 신뢰도가 낮으므로 human_review로 분기합니다.
    todolist.md P1: 문의 유형별 최소 근거 수 조건 강화.
    """
    current = _state(state)
    if current.target_route == "urgent_alert" or current.analysis.target_route == "urgent_alert":
        return "urgent_alert"
    if len(current.retrieved_docs) < _MIN_EVIDENCE_COUNT:
        return "human_review"
    return "save_evidence_docs"


def route_by_approval(state: OperationState) -> ApprovalRoute:
    """안전성 검수 결과에 따른 후속 route를 반환합니다.

    `APPROVAL_ROUTE_TARGETS`와 연결되어 최종 발행, 사람 검수, 긴급 알림 중 하나를 선택합니다.
    """
    current = _state(state)
    if current.approval_route is None:
        raise ValueError("approval_route is required for routing")
    return cast(ApprovalRoute, current.approval_route)


def route_after_retry(state: OperationState) -> Literal["query_router", "urgent_alert_node"]:
    """재시도 횟수 상한 초과 여부에 따라 재라우팅 또는 긴급 알림으로 분기합니다.

    retry_routing_node가 approval_route=urgent_alert 플래그를 세우는 조건과 동일하게
    retry_count >= max_retries를 직접 확인합니다 (todolist.md P0: 조건 일관성 통일).
    플래그만 의존할 경우 max_retries 변경 시 라우터가 이를 감지하지 못하는 문제를 방지합니다.
    """
    current = _state(state)
    retry_count = current.retry_count or 0
    max_retries = current.max_retries if current.max_retries is not None else 3
    if current.approval_route == "urgent_alert" or retry_count >= max_retries:
        return "urgent_alert_node"
    return "query_router"


def route_by_human_decision(state: OperationState) -> HumanDecision:
    """사람 검수 결정에 따른 후속 route를 반환합니다.

    `HUMAN_DECISION_TARGETS`와 연결되어 승인 발행, 재시도, 편집 반영 흐름으로 분기합니다.
    """
    current = _state(state)
    if current.human_decision is None:
        raise ValueError("human_decision is required for routing")
    return cast(HumanDecision, current.human_decision)


_RAW_NODE_FUNCTIONS: dict[str, NodeHandler] = {
    "load_ticket": load_ticket,
    "query_router": query_router,
    "payment_context_node": payment_context_node,
    "refund_context_node": refund_context_node,
    "item_delivery_context_node": item_delivery_context_node,
    "gacha_context_node": gacha_context_node,
    "policy_context_node": policy_context_node,
    "abuse_context_node": abuse_context_node,
    "outage_context_node": outage_context_node,
    "analyze_ticket": analyze_ticket,
    "save_analysis": save_analysis,
    "rag_retrieve_node": rag_retrieve_node,
    "generate_answer_node": generate_answer_node,
    "urgent_draft_node": urgent_draft_node,
    "save_draft_node": save_draft_node,
    "save_evidence_docs_node": save_evidence_docs_node,
    "approval_gate_node": approval_gate_node,
    "save_safety_result_node": save_safety_result_node,
    "publish_final_answer_node": publish_final_answer_node,
    "human_review_node": human_review_node,
    "retry_routing_node": retry_routing_node,
    "edit_answer_node": edit_answer_node,
    "save_final_edit_node": save_final_edit_node,
    "urgent_alert_node": urgent_alert_node,
}

NODE_FUNCTIONS: dict[str, NodeHandler] = {
    node_name: _with_node_logging(node_name, node_handler)
    for node_name, node_handler in _RAW_NODE_FUNCTIONS.items()
}
