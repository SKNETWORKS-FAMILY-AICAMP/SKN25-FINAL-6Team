"""답변 근거 retrieval agent.

`ticket_analysis.routing_target`에 따라 문서 근거, 운영 DB 근거,
또는 고정 안내 근거를 수집한다. 외부 LLM 호출 없이 LangChain LCEL
체인과 Pydantic 모델로 retrieval 계약을 고정한다.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableLambda
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from common.db.connection import db_connection


RoutingTarget = Literal["DB_only", "doc_only", "DB&DOC", "fixed_answer", "human_review"]


class RetrievalTicket(BaseModel):
    """근거 조회에 필요한 문의 식별자와 원문."""

    model_config = ConfigDict(extra="allow")

    ticket_id: int
    account_id: int | None = None
    user_id: int | None = None
    title: str | None = ""
    raw_query: str | None = ""
    source_type: str | None = ""


class RetrievalAnalysis(BaseModel):
    """ticket_analysis 결과 중 retrieval 경로 결정에 필요한 값."""

    model_config = ConfigDict(extra="allow")

    analysis_id: int | None = None
    category: str | None = "general"
    enriched_query: str | None = ""
    routing_target: RoutingTarget | str | None = "fixed_answer"
    summary: str | None = ""


class RetrievalRequest(BaseModel):
    """RetrievalRouter LCEL 체인의 입력 모델."""

    ticket: RetrievalTicket
    analysis: RetrievalAnalysis


class EvidenceItem(BaseModel):
    """answer_agent가 evidence_docs에 바로 저장할 수 있는 근거 모델."""

    source_type: str
    source_id: str | int | None = None
    evidence_text: str = Field(default="", max_length=3000)
    relevance_score: float = 0.0
    retrieval_rank: int = 1


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _query_terms(query: str) -> list[str]:
    # 너무 짧은 조사/기호는 제외하고 검색 조건을 안정화한다.
    terms = [term.strip() for term in query.replace("\n", " ").split(" ")]
    return [term for term in terms if len(term) >= 2][:6]


def _safe_text(value: object, limit: int = 600) -> str:
    return str(value or "").replace("\n", " ").strip()[:limit]


class DocumentRetriever:
    """documents/documents_chunks 기반 문서 검색기."""

    def search_hybrid_documents(
        self,
        query: str,
        category: str | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """dense 대체 검색과 키워드 검색 결과를 병합한다."""

        dense_results = self.search_dense_documents(query, category, source_type, limit)
        bm25_results = self.search_bm25_documents(query, category, source_type, limit)
        return self.merge_and_rerank_documents(query, dense_results, bm25_results)[: limit or 5]

    def search_dense_documents(
        self,
        query: str,
        category: str | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """현재 로컬 배치에서는 embedding 비용을 피하고 키워드 검색을 dense 후보로 재사용한다."""

        rows = self.search_bm25_documents(query, category, source_type, limit)
        for row in rows:
            row["dense_score"] = row.get("relevance_score", 0.0)
        return rows

    def search_bm25_documents(
        self,
        query: str,
        category: str | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """PostgreSQL ILIKE 조건으로 문서 chunk 후보를 조회한다."""

        clauses = ["TRUE"]
        params: list[Any] = []
        if category:
            clauses.append("LOWER(COALESCE(d.category, '')) = LOWER(%s)")
            params.append(category)
        if source_type:
            clauses.append("LOWER(COALESCE(d.source_type, '')) = LOWER(%s)")
            params.append(source_type)

        terms = _query_terms(query)
        if terms:
            term_clauses = []
            for term in terms:
                term_clauses.append("(c.chunk_text ILIKE %s OR d.title ILIKE %s OR d.raw_content ILIKE %s)")
                params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
            clauses.append("(" + " OR ".join(term_clauses) + ")")

        params.append(limit or 5)
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                rows = _fetch_all(
                    cur,
                    f"""
                    SELECT
                        c.chunk_id,
                        c.document_id,
                        c.chunk_text,
                        c.chunk_order,
                        d.source_type,
                        d.category,
                        d.title,
                        d.source_url,
                        d.published_at,
                        d.updated_at
                    FROM documents_chunks c
                    JOIN documents d ON d.documents_id = c.document_id
                    WHERE {" AND ".join(clauses)}
                    ORDER BY d.updated_at DESC NULLS LAST, c.chunk_order ASC
                    LIMIT %s
                    """,
                    tuple(params),
                )

        return [
            {
                **row,
                "bm25_score": float((limit or 5) - index),
                "relevance_score": max(0.1, 1.0 - (index * 0.1)),
                "retrieval_rank": index + 1,
            }
            for index, row in enumerate(rows)
        ]

    def merge_and_rerank_documents(
        self,
        query: str,
        dense_results: list[dict[str, object]],
        bm25_results: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """중복 chunk를 합치고 relevance_score 기준으로 재정렬한다."""

        by_chunk: dict[str, dict[str, object]] = {}
        for source_name, results in (("dense", dense_results), ("bm25", bm25_results)):
            for row in results:
                chunk_id = str(row.get("chunk_id") or "")
                if not chunk_id:
                    continue
                current = by_chunk.setdefault(chunk_id, {**row, "retrieval_sources": []})
                current["retrieval_sources"] = [*current.get("retrieval_sources", []), source_name]
                current["relevance_score"] = max(
                    float(current.get("relevance_score") or 0.0),
                    float(row.get("relevance_score") or row.get("bm25_score") or 0.0),
                )

        ranked = sorted(by_chunk.values(), key=lambda item: float(item.get("relevance_score") or 0.0), reverse=True)
        for index, row in enumerate(ranked):
            row["retrieval_rank"] = index + 1
        return ranked

    def fetch_document_chunks(self, chunk_ids: list[str]) -> list[dict[str, object]]:
        """검색된 chunk_id 목록으로 원문과 문서 메타데이터를 조회한다."""

        if not chunk_ids:
            return []
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_all(
                    cur,
                    """
                    SELECT
                        c.chunk_id,
                        c.document_id,
                        c.chunk_text,
                        c.token_count,
                        c.chunk_order,
                        d.source_type,
                        d.category,
                        d.title,
                        d.source_url,
                        d.published_at,
                        d.updated_at
                    FROM documents_chunks c
                    JOIN documents d ON d.documents_id = c.document_id
                    WHERE c.chunk_id = ANY(%s)
                    ORDER BY c.document_id ASC, c.chunk_order ASC
                    """,
                    (chunk_ids,),
                )

    def format_document_evidence(self, search_results: list[dict[str, object]]) -> list[dict[str, object]]:
        """문서 검색 결과를 EvidenceItem 목록으로 변환한다."""

        items = [
            EvidenceItem(
                source_type=str(row.get("source_type") or "documents"),
                source_id=row.get("chunk_id") or row.get("document_id"),
                evidence_text=f"{_safe_text(row.get('title'), 120)}: {_safe_text(row.get('chunk_text'), 900)}",
                relevance_score=float(row.get("relevance_score") or 0.0),
                retrieval_rank=int(row.get("retrieval_rank") or index + 1),
            )
            for index, row in enumerate(search_results)
        ]
        return [item.model_dump() for item in items]


class OperationLogRetriever:
    """payments/refunds/item_delivery_logs/gacha_logs 운영 DB 검색기."""

    def fetch_account_context(self, ticket: dict[str, object]) -> dict[str, object]:
        """문의의 user_id/account_id에 연결된 게임 계정 맥락을 조회한다."""

        account_id = ticket.get("account_id")
        user_id = ticket.get("user_id")
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_one(
                    cur,
                    """
                    SELECT
                        u.user_id,
                        u.nickname,
                        u.user_status,
                        a.account_id,
                        a.game_name,
                        a.uid,
                        a.server_region,
                        a.progression_level,
                        a.account_status
                    FROM community_users u
                    LEFT JOIN game_accounts a ON a.user_id = u.user_id
                    WHERE (%s IS NOT NULL AND a.account_id = %s)
                       OR (%s IS NOT NULL AND u.user_id = %s)
                    ORDER BY a.created_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (account_id, account_id, user_id, user_id),
                ) or {"user_id": user_id, "account_id": account_id, "lookup_status": "not_found"}

    def fetch_payment_logs(self, account_id: int) -> list[dict[str, object]]:
        """계정 기준 결제 로그를 최신순으로 조회한다."""

        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_all(
                    cur,
                    """
                    SELECT payment_id, account_id, product_name, product_type, amount, currency,
                           payment_method, payment_status, transaction_id, paid_at
                    FROM payments
                    WHERE account_id = %s
                    ORDER BY paid_at DESC NULLS LAST, payment_id DESC
                    LIMIT 20
                    """,
                    (account_id,),
                )

    def fetch_refund_logs(self, payment_ids: list[int]) -> list[dict[str, object]]:
        """결제 ID 목록 기준 환불 로그를 조회한다."""

        if not payment_ids:
            return []
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_all(
                    cur,
                    """
                    SELECT refund_id, payment_id, refund_status, refund_reason, requested_at, processed_at
                    FROM refunds
                    WHERE payment_id = ANY(%s)
                    ORDER BY requested_at DESC NULLS LAST, refund_id DESC
                    """,
                    (payment_ids,),
                )

    def fetch_item_delivery_logs(self, account_id: int, payment_ids: list[int] | None = None) -> list[dict[str, object]]:
        """아이템 지급 로그를 계정과 결제 ID 조건으로 조회한다."""

        clauses = ["account_id = %s"]
        params: list[Any] = [account_id]
        if payment_ids:
            clauses.append("payment_id = ANY(%s)")
            params.append(payment_ids)
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_all(
                    cur,
                    f"""
                    SELECT delivery_id, payment_id, account_id, source_type, item_name, quantity,
                           delivery_status, expected_at, delivered_at
                    FROM item_delivery_logs
                    WHERE {" AND ".join(clauses)}
                    ORDER BY expected_at DESC NULLS LAST, delivery_id DESC
                    LIMIT 20
                    """,
                    tuple(params),
                )

    def fetch_gacha_logs(self, account_id: int) -> list[dict[str, object]]:
        """가챠/뽑기 관련 계정 로그를 조회한다."""

        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return _fetch_all(
                    cur,
                    """
                    SELECT gacha_id, account_id, banner_name, item_name, item_type, rarity, pity_count, pulled_at
                    FROM gacha_logs
                    WHERE account_id = %s
                    ORDER BY pulled_at DESC NULLS LAST, gacha_id DESC
                    LIMIT 20
                    """,
                    (account_id,),
                )

    def build_text_to_sql_plan(self, question: str, analysis: dict[str, object]) -> dict[str, object]:
        """자연어 문의를 허용된 고정 SELECT 계획으로만 변환한다."""

        category = str(analysis.get("category") or "").lower()
        tables = ["payments", "item_delivery_logs"]
        if "refund" in category or "환불" in question:
            tables.append("refunds")
        if "gacha" in category or "가챠" in question or "뽑기" in question:
            tables.append("gacha_logs")
        return {"query_type": "fixed_select", "tables": tables, "account_id": analysis.get("account_id")}

    def execute_text_to_sql(self, sql_plan: dict[str, object]) -> list[dict[str, object]]:
        """허용된 테이블에 대해서만 고정 조회 계획을 실행한다."""

        account_id = sql_plan.get("account_id")
        if account_id is None:
            return []
        rows: list[dict[str, object]] = []
        for table in sql_plan.get("tables") or []:
            if table == "payments":
                rows.extend({**row, "_source_type": table} for row in self.fetch_payment_logs(int(account_id)))
            if table == "item_delivery_logs":
                rows.extend({**row, "_source_type": table} for row in self.fetch_item_delivery_logs(int(account_id)))
            if table == "gacha_logs":
                rows.extend({**row, "_source_type": table} for row in self.fetch_gacha_logs(int(account_id)))
        return rows

    def run_fixed_sql_lookup(self, ticket: dict[str, object], analysis: dict[str, object]) -> dict[str, object]:
        """계정 맥락과 주요 운영 로그를 한 번에 조회한다."""

        account_context = self.fetch_account_context(ticket)
        account_id = account_context.get("account_id")
        payment_logs = self.fetch_payment_logs(int(account_id)) if account_id is not None else []
        payment_ids = [int(row["payment_id"]) for row in payment_logs if row.get("payment_id") is not None]
        refund_logs = self.fetch_refund_logs(payment_ids)
        item_delivery_logs = self.fetch_item_delivery_logs(int(account_id), payment_ids) if account_id is not None else []
        gacha_logs = self.fetch_gacha_logs(int(account_id)) if account_id is not None else []
        return {
            "account_context": account_context,
            "payments": payment_logs,
            "refunds": refund_logs,
            "item_delivery_logs": item_delivery_logs,
            "gacha_logs": gacha_logs,
        }

    def detect_payment_delivery_gap(self, operation_logs: dict[str, object]) -> dict[str, object]:
        """결제 성공 후 지급 완료 로그가 없는 결제 ID를 찾는다."""

        payments = operation_logs.get("payments") or []
        deliveries = operation_logs.get("item_delivery_logs") or []
        paid_ids = {
            row.get("payment_id")
            for row in payments
            if str(row.get("payment_status") or "").lower() in {"paid", "success", "completed", "complete"}
        }
        delivered_ids = {
            row.get("payment_id")
            for row in deliveries
            if str(row.get("delivery_status") or "").lower() in {"delivered", "success", "completed", "complete"}
        }
        gap_ids = sorted(str(payment_id) for payment_id in paid_ids if payment_id is not None and payment_id not in delivered_ids)
        return {"has_gap": bool(gap_ids), "payment_ids": gap_ids, "review_required": bool(gap_ids)}

    def format_db_evidence(self, query_plan: dict[str, object], rows: list[dict[str, object]]) -> list[dict[str, object]]:
        """운영 DB 조회 결과를 민감값을 줄인 EvidenceItem 목록으로 변환한다."""

        items = []
        for index, row in enumerate(rows):
            source_type = str(row.get("_source_type") or query_plan.get("source_type") or "operation_db")
            visible_pairs = []
            for key, value in row.items():
                if key in {"transaction_id", "_source_type"}:
                    continue
                visible_pairs.append(f"{key}={_safe_text(value, 80)}")
            items.append(
                EvidenceItem(
                    source_type=source_type,
                    source_id=row.get("payment_id") or row.get("refund_id") or row.get("delivery_id") or row.get("gacha_id") or index + 1,
                    evidence_text="; ".join(visible_pairs),
                    relevance_score=0.7,
                    retrieval_rank=index + 1,
                ).model_dump()
            )
        return items


class RetrievalRouter:
    """routing_target별 검색 함수를 LCEL 체인으로 연결한다."""

    def __init__(self) -> None:
        self.document_retriever = DocumentRetriever()
        self.operation_retriever = OperationLogRetriever()
        self.chain = RunnableLambda(RetrievalRequest.model_validate) | RunnableLambda(self._route_request)

    def select_retrieval_functions(self, analysis: dict[str, object]) -> list[str]:
        """routing_target 기준으로 사용할 retrieval 함수명을 반환한다."""

        routing_target = str(analysis.get("routing_target") or "fixed_answer")
        if routing_target == "DB_only":
            return ["retrieve_db_only"]
        if routing_target == "doc_only":
            return ["retrieve_doc_only"]
        if routing_target == "DB&DOC":
            return ["retrieve_db_and_doc"]
        return ["retrieve_fixed_answer_context"]

    def retrieve_by_routing_target(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        """외부 호출용 단일 진입점."""

        request = {"ticket": ticket, "analysis": analysis}
        return self.chain.invoke(request)

    def _route_request(self, request: RetrievalRequest) -> list[dict[str, object]]:
        routing_target = str(request.analysis.routing_target or "fixed_answer")
        ticket = request.ticket.model_dump()
        analysis = request.analysis.model_dump()
        if routing_target == "DB_only":
            return self.retrieve_db_only(ticket, analysis)
        if routing_target == "doc_only":
            return self.retrieve_doc_only(ticket, analysis)
        if routing_target == "DB&DOC":
            return self.retrieve_db_and_doc(ticket, analysis)
        return self.retrieve_fixed_answer_context(ticket, analysis)

    def retrieve_db_only(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        """운영 DB 근거만 수집한다."""

        operation_logs = self.operation_retriever.run_fixed_sql_lookup(ticket, analysis)
        rows: list[dict[str, object]] = []
        for source_type in ("payments", "refunds", "item_delivery_logs", "gacha_logs"):
            rows.extend({**row, "_source_type": source_type} for row in operation_logs.get(source_type, []))
        gap = self.operation_retriever.detect_payment_delivery_gap(operation_logs)
        if gap["has_gap"]:
            rows.insert(0, {"_source_type": "operation_gap", "gap_payment_ids": ",".join(gap["payment_ids"])})
        return self.operation_retriever.format_db_evidence({"source_type": "operation_db"}, rows)

    def retrieve_doc_only(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        """문서 근거만 수집한다."""

        query = str(analysis.get("enriched_query") or ticket.get("raw_query") or ticket.get("title") or "")
        results = self.document_retriever.search_hybrid_documents(query, str(analysis.get("category") or "") or None, None, 5)
        return self.document_retriever.format_document_evidence(results)

    def retrieve_db_and_doc(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        """운영 DB 근거와 문서 근거를 모두 수집해 한 ranking으로 합친다."""

        merged = [*self.retrieve_db_only(ticket, analysis), *self.retrieve_doc_only(ticket, analysis)]
        for index, row in enumerate(merged):
            row["retrieval_rank"] = index + 1
        return merged

    def retrieve_fixed_answer_context(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        """검색 없이 운영자 확인 안내에 필요한 최소 맥락을 만든다."""

        item = EvidenceItem(
            source_type="fixed_answer",
            source_id=str(ticket.get("ticket_id")),
            evidence_text=(
                "근거 자동 조회 대신 운영자 확인이 필요한 문의입니다. "
                f"분석 요약: {_safe_text(analysis.get('summary'), 1000)}"
            ),
            relevance_score=0.1,
            retrieval_rank=1,
        )
        return [item.model_dump()]
