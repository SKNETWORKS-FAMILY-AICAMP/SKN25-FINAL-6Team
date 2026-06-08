"""CS 문의 분석 agent.

Airflow 배치가 호출하는 1단계 agent이다. 아직 분석되지 않은
`qa_ticket`을 읽고, LangChain LCEL 체인과 Pydantic 모델로 문의를
정규화한 뒤 `ticket_analysis`에 저장한다.
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, ConfigDict

from common.db.connection import db_connection


Category = Literal["payment", "refund", "account", "bug", "gacha", "policy", "general"]
RoutingTarget = Literal["DB_only", "doc_only", "DB&DOC", "fixed_answer", "human_review"]
Sentiment = Literal["positive", "neutral", "negative"]
RiskLevel = Literal["LOW", "MID", "HIGH"]


class TicketPayload(BaseModel):
    """DB에서 읽은 qa_ticket 1건을 분석 체인 입력으로 고정한다."""

    model_config = ConfigDict(extra="allow")

    ticket_id: int
    account_id: int | None = None
    user_id: int | None = None
    title: str | None = ""
    raw_query: str | None = ""
    source_type: str | None = ""
    status: str | None = ""
    session_id: str | None = None
    responder_type: str | None = "agent"


class EnrichedTicket(BaseModel):
    """분류와 라우팅에 쓰기 좋은 텍스트를 포함한 중간 상태."""

    ticket: TicketPayload
    enriched_query: str
    normalized_query: str


class AnalysisResult(BaseModel):
    """ticket_analysis 테이블에 저장할 분석 결과."""

    ticket_id: int
    category: Category
    responder_type: str = "agent"
    enriched_query: str
    risk_level: RiskLevel
    sentiment: Sentiment
    routing_target: RoutingTarget
    summary: str


CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    "payment": ("결제", "구매", "충전", "미지급", "상품", "패키지", "쿠폰", "영수증", "다이아"),
    "refund": ("환불", "취소", "청약철회", "반품", "결제 취소"),
    "account": ("계정", "로그인", "연동", "복구", "인증", "정지", "탈퇴", "비밀번호"),
    "bug": ("버그", "오류", "렉", "튕김", "접속", "강제 종료", "채팅", "서버"),
    "gacha": ("가챠", "뽑기", "확률", "천장", "소환", "픽업"),
    "policy": ("정책", "제재", "운영", "공지", "약관", "신고"),
    "general": (),
}

NEGATIVE_KEYWORDS = ("화남", "짜증", "불만", "최악", "고소", "신고", "빨리", "장난", "문제")
POSITIVE_KEYWORDS = ("감사", "고맙", "좋아요", "확인 부탁", "문의드립니다")
HIGH_RISK_KEYWORDS = ("고소", "신고", "환불 거부", "계정 정지", "중복 결제", "미지급", "개인정보", "약관 위반")


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    # 현재 workflow write 테이블은 DB 기본값이 없을 수 있어 배치 안에서 다음 ID를 계산한다.
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row["next_id"])


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)


def _normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text[:4000]


def _to_ticket_payload(ticket: dict[str, object] | TicketPayload) -> TicketPayload:
    return TicketPayload.model_validate(ticket)


def _build_enriched_ticket(ticket: TicketPayload) -> EnrichedTicket:
    # title과 raw_query를 함께 보존해 분류 키워드 손실을 줄인다.
    combined = _normalize_text(f"{ticket.title or ''}\n{ticket.raw_query or ''}")
    return EnrichedTicket(ticket=ticket, enriched_query=combined, normalized_query=combined.lower())


def _classify_category(enriched: EnrichedTicket) -> Category:
    scores = {
        category: _keyword_score(enriched.normalized_query, keywords)
        for category, keywords in CATEGORY_KEYWORDS.items()
        if category != "general"
    }
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else "general"


def _score_sentiment(enriched: EnrichedTicket) -> Sentiment:
    text = enriched.normalized_query
    if _contains_any(text, NEGATIVE_KEYWORDS):
        return "negative"
    if _contains_any(text, POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def _score_risk(enriched: EnrichedTicket, category: Category) -> RiskLevel:
    text = enriched.normalized_query
    if _contains_any(text, HIGH_RISK_KEYWORDS):
        return "HIGH"
    if category in {"payment", "refund", "account"}:
        return "MID"
    return "LOW"


def _decide_routing(enriched: EnrichedTicket, category: Category, risk_level: RiskLevel) -> RoutingTarget:
    # 카페 외 채널은 자동 게시 대상이 아니므로 운영자 검토로 보낸다.
    if enriched.ticket.source_type != "naver_cafe":
        return "human_review"
    if risk_level == "HIGH":
        return "DB&DOC"
    if category in {"payment", "refund", "account", "gacha"}:
        return "DB&DOC"
    if category in {"bug", "policy"}:
        return "doc_only"
    return "fixed_answer"


def _summarize(enriched: EnrichedTicket, category: Category, routing_target: RoutingTarget, sentiment: Sentiment, risk_level: RiskLevel) -> str:
    return (
        f"문의는 {category} 유형으로 분류되며 응답 근거 경로는 {routing_target}입니다. "
        f"감성은 {sentiment}, 위험도는 {risk_level}로 판단됩니다. "
        "운영자는 원문과 계정/결제/정책 근거를 확인한 뒤 답변 초안을 검토해야 합니다."
    )


def _build_analysis_result(parts: dict[str, object]) -> AnalysisResult:
    enriched = EnrichedTicket.model_validate(parts["enriched"])
    category = parts["category"]
    sentiment = parts["sentiment"]
    risk_level = parts["risk_level"]
    routing_target = parts["routing_target"]
    return AnalysisResult(
        ticket_id=enriched.ticket.ticket_id,
        category=category,
        responder_type=enriched.ticket.responder_type or "agent",
        enriched_query=enriched.enriched_query,
        risk_level=risk_level,
        sentiment=sentiment,
        routing_target=routing_target,
        summary=_summarize(enriched, category, routing_target, sentiment, risk_level),
    )


def build_analysis_chain():
    """문의 1건을 AnalysisResult로 변환하는 LCEL 체인."""

    enrich_chain = RunnableLambda(_to_ticket_payload) | RunnableLambda(_build_enriched_ticket)
    parallel_chain = RunnableParallel(
        enriched=RunnablePassthrough(),
        category=RunnableLambda(_classify_category),
        sentiment=RunnableLambda(_score_sentiment),
        risk_level=RunnableLambda(lambda enriched: _score_risk(enriched, _classify_category(enriched))),
        routing_target=RunnableLambda(
            lambda enriched: _decide_routing(
                enriched,
                _classify_category(enriched),
                _score_risk(enriched, _classify_category(enriched)),
            )
        ),
    )
    return enrich_chain | parallel_chain | RunnableLambda(_build_analysis_result)


ANALYSIS_CHAIN = build_analysis_chain()


def run_analysis_agent() -> None:
    """분석되지 않은 문의를 순차 처리하고 배치 결과를 운영 로그에 남긴다."""

    targets = fetch_unanalyzed_tickets()
    processed = 0
    for ticket in targets:
        analysis = analyze_ticket(ticket)
        saved = save_ticket_analysis(analysis)
        mark_ticket_analysis_completed(int(saved["ticket_id"]), int(saved["analysis_id"]))
        processed += 1

    log_analysis_batch_event({"target_count": len(targets), "processed_count": processed})


def fetch_unanalyzed_tickets() -> list[dict[str, object]]:
    """ticket_analysis가 아직 연결되지 않은 qa_ticket 목록을 조회한다."""

    limit = int(os.environ.get("CS_AUTO_ANALYSIS_BATCH_LIMIT", "50"))
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
                    t.responder_type
                FROM qa_ticket t
                LEFT JOIN ticket_analysis a ON a.ticket_id = t.ticket_id
                WHERE a.analysis_id IS NULL
                ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                LIMIT %s
                """,
                (limit,),
            )


def analyze_ticket(ticket: dict[str, object]) -> dict[str, object]:
    """LCEL 분석 체인을 실행해 저장 가능한 dict payload를 만든다."""

    return ANALYSIS_CHAIN.invoke(ticket).model_dump()


def build_enriched_query(ticket: dict[str, object]) -> str:
    """기존 호출부 호환용 helper."""

    return _build_enriched_ticket(TicketPayload.model_validate(ticket)).enriched_query


def classify_ticket_category(ticket: dict[str, object], enriched_query: str) -> str:
    """기존 호출부 호환용 category 분류 helper."""

    payload = TicketPayload.model_validate({**ticket, "raw_query": enriched_query})
    return _classify_category(_build_enriched_ticket(payload))


def decide_routing_target(ticket: dict[str, object], category: str, enriched_query: str) -> str:
    """기존 호출부 호환용 routing helper."""

    enriched = _build_enriched_ticket(TicketPayload.model_validate({**ticket, "raw_query": enriched_query}))
    risk = _score_risk(enriched, category)
    return _decide_routing(enriched, category, risk)


def score_sentiment(ticket: dict[str, object], enriched_query: str) -> str:
    """기존 호출부 호환용 sentiment helper."""

    payload = TicketPayload.model_validate({**ticket, "raw_query": enriched_query})
    return _score_sentiment(_build_enriched_ticket(payload))


def score_risk_level(ticket: dict[str, object], enriched_query: str, category: str) -> str:
    """기존 호출부 호환용 risk helper."""

    payload = TicketPayload.model_validate({**ticket, "raw_query": enriched_query})
    return _score_risk(_build_enriched_ticket(payload), category)


def summarize_ticket_analysis(
    ticket: dict[str, object],
    enriched_query: str,
    category: str,
    routing_target: str,
    sentiment: str,
    risk_level: str,
) -> str:
    """기존 호출부 호환용 summary helper."""

    payload = TicketPayload.model_validate({**ticket, "raw_query": enriched_query})
    return _summarize(_build_enriched_ticket(payload), category, routing_target, sentiment, risk_level)


def build_ticket_analysis_payload(
    ticket: dict[str, object],
    enriched_query: str,
    category: str,
    routing_target: str,
    sentiment: str,
    risk_level: str,
    summary: str,
) -> dict[str, object]:
    """ticket_analysis 저장 payload를 명시 모델로 검증한다."""

    payload = AnalysisResult(
        ticket_id=int(ticket["ticket_id"]),
        category=category,
        responder_type=str(ticket.get("responder_type") or "agent"),
        enriched_query=enriched_query,
        risk_level=risk_level,
        sentiment=sentiment,
        routing_target=routing_target,
        summary=summary,
    )
    return payload.model_dump()


def save_ticket_analysis(payload: dict[str, object]) -> dict[str, object]:
    """분석 결과를 ticket_analysis에 저장한다."""

    analysis = AnalysisResult.model_validate(payload)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            analysis_id = _next_integer_id(cur, "ticket_analysis", "analysis_id")
            cur.execute(
                """
                INSERT INTO ticket_analysis (
                    analysis_id,
                    ticket_id,
                    category,
                    responder_type,
                    enriched_query,
                    risk_level,
                    sentiment,
                    routing_target,
                    summary,
                    analyzed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING analysis_id, ticket_id
                """,
                (
                    analysis_id,
                    analysis.ticket_id,
                    analysis.category,
                    analysis.responder_type,
                    analysis.enriched_query,
                    analysis.risk_level,
                    analysis.sentiment,
                    analysis.routing_target,
                    analysis.summary,
                ),
            )
            row = cur.fetchone()
    return dict(row)


def mark_ticket_analysis_completed(ticket_id: int, analysis_id: int) -> None:
    """분석 완료 상태와 이벤트 로그를 기록한다."""

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                  AND COALESCE(status, '') <> %s
                """,
                ("analyzed", ticket_id, "resolved"),
            )
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
                    "cs_auto_analysis_agent",
                    "ticket_analyzed",
                    "success",
                    Json({"analysis_id": analysis_id}),
                ),
            )


def log_analysis_batch_event(batch_result: dict[str, object]) -> None:
    """배치 처리 건수만 기록하고 원문 문의 전문은 로그에 남기지 않는다."""

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
                    "cs_auto_analysis_agent",
                    "analysis_batch_completed",
                    "success",
                    Json(batch_result),
                ),
            )
