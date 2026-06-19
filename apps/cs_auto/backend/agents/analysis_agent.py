"""CS 문의 분석 agent.

Airflow 배치가 호출하는 1단계 agent이다. 아직 분석되지 않은
`qa_ticket`을 읽고, LangChain LCEL 체인과 Pydantic 모델로 문의를
정규화한 뒤 `ticket_analysis`에 저장한다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict
import yaml

from common.db.connection import db_connection
from common.observability.langsmith import configure_langsmith


configure_langsmith("operation")


Category = Literal["payment", "refund", "account", "bug", "gacha", "policy", "general"]
# routing_target은 답변 생성 단계에서 어떤 근거를 조회할지 결정하는 값이다.
RoutingTarget = Literal["DB_only", "doc_only", "DB&DOC", "fixed_answer"]
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
    session_id: str | int | None = None


class EnrichedTicket(BaseModel):
    """분류와 라우팅에 쓰기 좋은 텍스트를 포함한 중간 상태."""

    ticket: TicketPayload
    enriched_query: str
    normalized_query: str


class AnalysisResult(BaseModel):
    """ticket_analysis 테이블에 저장할 분석 결과."""

    ticket_id: int
    category: Category
    enriched_query: str
    risk_level: RiskLevel
    sentiment: Sentiment
    # chatbot처럼 별도 답변 근거 경로가 필요 없는 경우에는 None을 저장한다.
    routing_target: RoutingTarget | None = None
    summary: str


class RoutingDecision(BaseModel):
    """Pydantic parser가 검증하는 라우팅 결정 결과."""

    routing_target: RoutingTarget | None = None
    reason: str = ""


class CategoryDecision(BaseModel):
    category: Category
    reason: str = ""


AnalysisResult.model_rebuild()
RoutingDecision.model_rebuild()
CategoryDecision.model_rebuild()


KEYWORD_ROOT = Path(os.environ.get("CS_AUTO_KEYWORD_DIR", Path(__file__).resolve().parents[4] / "data" / "keywords"))


def _load_keyword_yaml(relative_path: str) -> dict[str, Any]:
    path = KEYWORD_ROOT / relative_path
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Keyword YAML must be a mapping: {path}")
    return raw_data


def _load_keyword_list(relative_path: str) -> tuple[str, ...]:
    data = _load_keyword_yaml(relative_path)
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list):
        raise ValueError(f"Keyword YAML value must be a list: {relative_path}.keywords")
    return tuple(
        keyword.strip()
        for keyword in (str(item) for item in keywords)
        if keyword.strip()
    )

CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    "payment": _load_keyword_list("category/payment.yaml"),
    "refund": _load_keyword_list("category/refund.yaml"),
    "account": _load_keyword_list("category/account.yaml"),
    "bug": _load_keyword_list("category/bug.yaml"),
    "gacha": _load_keyword_list("category/gacha.yaml"),
    "policy": _load_keyword_list("category/policy.yaml"),
    "general": (),
}

NEGATIVE_KEYWORDS = _load_keyword_list("sentiment/negative.yaml")
POSITIVE_KEYWORDS = _load_keyword_list("sentiment/positive.yaml")
HIGH_RISK_KEYWORDS = _load_keyword_list("risk/high.yaml")


## 카테고리 분류!  - YAML 유지보수?

CATEGORY_DECISION_PARSER = PydanticOutputParser(pydantic_object=CategoryDecision)
CATEGORY_PROMPT = PromptTemplate(
    input_variables=["context_json"],
    partial_variables={"format_instructions": CATEGORY_DECISION_PARSER.get_format_instructions()},
    template="""다음 CS 문의를 하나의 category로 분류하세요.

허용 category:
- payment: 결제, 충전, 영수증, 카드 승인, 결제 실패
- refund: 환불, 취소, 환불 지연, 결제 취소
- account: 로그인, 비밀번호, 계정 잠김, 인증, 회원정보
- bug: 오류, 버그, 기능 미동작, 접속 이상, UI/게임 실행 문제
- gacha: 가챠, 뽑기, 배너, 확률, 보상 지급 관련 문의
- policy: 운영 정책, 이용 제한, 제재 기준, 약관, 공지/규정 문의
- general: 위 항목으로 보기 어려운 일반 문의

분류 입력:
<category_context>
{context_json}
</category_context>

반드시 아래 JSON 형식 지시를 따르세요.
{format_instructions}
""",
)


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


def _classify_category_by_keywords(enriched: EnrichedTicket) -> Category:
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


"""
항상 확장성을 고려하여 하드코딩할 것. 구현되지 않더라도 발표나, 그걸 고려했다는 흔적을 남길 필요가 있음
이전버전으로 언제든지 ROLLBACK 할 수 있어야하며, 변경 history도 필요하다.

운영자들이 업로드하면 자동으로 코드에 적용되게 자동화를 적용할 수 있는걸 적용할 수 있는지?에 대해서 고려해보았는가???

"""


# LLM 응답을 RoutingDecision 모델로 강제 파싱해 허용된 routing_target만 저장한다.
ROUTING_DECISION_PARSER = PydanticOutputParser(pydantic_object=RoutingDecision)

# 분석 결과를 LLM에 넘겨 DB, 문서, 복합 근거, 고정 답변 중 사용할 경로를 고르게 한다.
ROUTING_PROMPT = PromptTemplate(
    input_variables=["context_json"],
    partial_variables={"format_instructions": ROUTING_DECISION_PARSER.get_format_instructions()},
    template="""CS 문의 분석 결과를 보고 다음 응답 근거 경로를 결정하세요.

허용값:
- "DB_only": 계정, 결제, 지급, 가챠 등 운영 DB 확인이 주 근거인 경우
- "doc_only": 공지, 정책, 약관, 일반 장애 안내 등 문서 근거가 주 근거인 경우 
- "DB&DOC": 운영 DB와 문서 근거가 모두 필요한 경우
- "fixed_answer": 답변할 근거가 없거나 짧은 잡담/테스트/아무말인 경우
- null: source_type이 chatbot인 경우에만 사용

판단 입력:
<routing_context>
{context_json}
</routing_context>

반드시 아래 형식 지침을 따르세요.
{format_instructions}
""",
)


def _build_routing_prompt_input(parts: dict[str, object]) -> dict[str, str]:
    # 앞 단계에서 계산한 분석값만 추려 LLM 라우팅 판단 입력으로 만든다.
    enriched = EnrichedTicket.model_validate(parts["enriched"])
    context = {
        "source_type": enriched.ticket.source_type,
        "category": parts["category"],
        "sentiment": parts["sentiment"],
        "risk_level": parts["risk_level"],
        "enriched_query": enriched.enriched_query,
    }
    return {"context_json": json.dumps(context, ensure_ascii=False)}


def _build_category_prompt_input(enriched: EnrichedTicket) -> dict[str, str]:
    keyword_hits = {
        category: [keyword for keyword in keywords if keyword and keyword in enriched.normalized_query][:10] #enriched/normalized.축소
        for category, keywords in CATEGORY_KEYWORDS.items()
        if category != "general"
    }
    context = {
        "source_type": enriched.ticket.source_type,
        "title": enriched.ticket.title,
        "raw_query": enriched.ticket.raw_query,
        "enriched_query": enriched.enriched_query,
        "keyword_hits": keyword_hits,
    }
    return {"context_json": json.dumps(context, ensure_ascii=False)}

"""
최종 구현 때에는 llm api가 동났을 때를 고려하여 exception도 작성하거나, 고려한 흔적이 필요하다.
"""

"""
LLM이 두 모델이 같다면, 파라미터만 다르게 사용한다면, 하나의 함수만 선언하기!
"""

def _routing_llm() -> ChatOpenAI:
    # 라우팅 판단 전용 LLM 설정이다. 별도 모델이 없으면 공통 LLM_MODEL을 사용한다.
    model = os.environ.get("CS_AUTO_ROUTING_MODEL") or os.environ["LLM_MODEL"]
    return ChatOpenAI(
        model=model,
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    )


def _category_llm() -> ChatOpenAI:
    model = os.environ.get("CS_AUTO_CATEGORY_MODEL") or os.environ.get("CS_AUTO_ROUTING_MODEL") or os.environ["LLM_MODEL"]
    return ChatOpenAI(
        model=model,
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    )


def _classify_category(enriched: EnrichedTicket) -> Category:
    chain = CATEGORY_PROMPT | _category_llm() | CATEGORY_DECISION_PARSER
    try:
        decision = chain.invoke(_build_category_prompt_input(enriched))
        return decision.category
    except Exception:
        return _classify_category_by_keywords(enriched)


def _add_routing_target(parts: dict[str, object]) -> dict[str, object]:
    # LCEL 체인으로 응답 근거 경로를 결정하고 기존 분석 중간값에 routing_target을 추가한다.
    chain = ROUTING_PROMPT | _routing_llm() | ROUTING_DECISION_PARSER
    decision = chain.invoke(_build_routing_prompt_input(parts))
    return {**parts, "routing_target": decision.routing_target}


def _summarize(
    enriched: EnrichedTicket,
    category: Category,
    routing_target: RoutingTarget | None,
    sentiment: Sentiment,
    risk_level: RiskLevel,
) -> str:
    if routing_target is None:
        return (
            f"문의는 {category} 유형으로 분류됩니다. "
            f"감성은 {sentiment}, 위험도는 {risk_level}로 판단됩니다. "
            "chatbot 문의는 분석 단계에서 별도 응답 근거 경로를 생성하지 않습니다."
        )
    return (
        f"문의는 {category} 유형으로 분류되며 응답 근거는 {routing_target}입니다. "
        f"감성은 {sentiment}, 위험도는 {risk_level}로 판단됩니다. "
        "운영자는 원문과 계정/결제/정책 근거를 확인한 뒤 답변 초안을 검토해야 합니다."
    )


def build_analysis_result(ticket: dict[str, object] | TicketPayload) -> AnalysisResult:
    """문의 1건을 AnalysisResult로 변환한다."""

    # 1. 원본 티켓을 검증하고 제목+본문을 분석 가능한 텍스트로 정규화한다.
    enriched = _build_enriched_ticket(_to_ticket_payload(ticket))

    # 2. 키워드 기반으로 카테고리, 감성, 위험도를 먼저 계산한다.
    category = _classify_category(enriched)
    sentiment = _score_sentiment(enriched)
    risk_level = _score_risk(enriched, category)

    # 3. 계산된 분석값을 바탕으로 답변 생성에 필요한 근거 경로를 LLM이 결정한다.
    routed = _add_routing_target(
        {
            "enriched": enriched,
            "category": category,
            "sentiment": sentiment,
            "risk_level": risk_level,
        }
    )
    routing_target = routed["routing_target"]

    # 4. ticket_analysis 테이블에 저장할 최종 분석 모델을 만든다.
    return AnalysisResult(
        ticket_id=enriched.ticket.ticket_id,
        category=category,
        enriched_query=enriched.enriched_query,
        risk_level=risk_level,
        sentiment=sentiment,
        routing_target=routing_target,
        summary=_summarize(enriched, category, routing_target, sentiment, risk_level),
    )


def run_analysis_agent() -> None:
    """분석되지 않은 문의를 순차 처리한다."""

    targets = fetch_unanalyzed_tickets()
    for ticket in targets:
        analysis = analyze_ticket(ticket)
        saved = save_ticket_analysis(analysis)
        # 분석 저장이 끝난 티켓은 재처리되지 않도록 qa_ticket 상태를 완료 처리한다.
        mark_ticket_analysis_completed(int(saved["ticket_id"]))


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
                    t.session_id
                FROM qa_ticket t
                LEFT JOIN ticket_analysis a ON a.ticket_id = t.ticket_id
                WHERE a.analysis_id IS NULL
                  AND LOWER(COALESCE(t.status, '')) <> 'collecting'
                ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                LIMIT %s
                """,
                (limit,),
            )


def analyze_ticket(ticket: dict[str, object]) -> dict[str, object]:
    """분석 파이프라인을 실행해 저장 가능한 dict payload를 만든다."""

    return build_analysis_result(ticket).model_dump()


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
                    "AI",
                    analysis.enriched_query,
                    analysis.risk_level,
                    analysis.sentiment,
                    analysis.routing_target,
                    analysis.summary,
                ),
            )
            row = cur.fetchone()
    return dict(row)


def mark_ticket_analysis_completed(ticket_id: int) -> None:
    """분석 완료 상태를 기록한다."""

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
