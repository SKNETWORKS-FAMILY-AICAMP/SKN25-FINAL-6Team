from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from common.db.connection import db_connection
from common.retrieval import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks


SharedCategory = Literal["payment", "bug", "faq", "voc"]

SAFE_FALLBACK_RESPONSE = "현재 문의는 자동 답변만으로 정확히 안내드리기 어려워 담당자가 확인 후 다시 안내드리겠습니다."
PAYMENT_FALLBACK_RESPONSE = (
    "결제 관련 문의는 계정 및 결제 내역 확인이 필요합니다. "
    "담당자가 결제 상태와 지급 여부를 확인할 수 있도록 접수하겠습니다."
)
BUG_FALLBACK_RESPONSE = (
    "게임 이용 중 발생한 문제는 기기 환경과 발생 상황 확인이 필요합니다. "
    "담당자가 재현 정보와 로그를 확인할 수 있도록 접수하겠습니다."
)
VOC_FIXED_RESPONSE = (
    "의견을 보내주셔서 감사합니다.\n"
    "보내주신 내용은 관련 부서에 전달하여 검토할 수 있도록 접수하겠습니다."
)

PAYMENT_SYSTEM_PROMPT = (
    "You are a Korean game customer-support drafting unit for payment, refund, item delivery, and gacha inquiries. "
    "Use only the provided evidence. "
    "Do not invent transaction status, refund status, compensation, or delivery completion. "
    "If evidence is missing or inconsistent, draft a conservative response that says an operator should review the ticket."
)
BUG_SYSTEM_PROMPT = (
    "You are a Korean game customer-support drafting unit for bug, incident, and account-specific troubleshooting inquiries. "
    "Use only the provided evidence. "
    "Do not confirm a bug, fix, compensation, or rollback unless the evidence supports it. "
    "If evidence is insufficient, ask for reproduction details or say an operator should review the case."
)
FAQ_SYSTEM_PROMPT = (
    "You are a Korean game customer-support FAQ/RAG drafting unit. "
    "Answer only with facts supported by the provided evidence. "
    "Do not answer from general model knowledge when evidence is unavailable. "
    "If the evidence does not explicitly answer the question, use a conservative fallback."
)


class SharedDraftRequest(BaseModel):
    category: SharedCategory
    query_text: str
    user_id: int | None = None
    account_id: int | None = None
    context_rows: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    is_actionable: bool | None = None
    should_use_rag: bool | None = None
    fallback_reason: str | None = None
    force_review: bool = False


class SharedDraftResult(BaseModel):
    draft_text: str
    reasoning_node: str
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class VocClassification(BaseModel):
    voc_type: Literal["suggestion", "complaint", "praise", "multi_intent", "other"]
    sentiment: Literal["positive", "neutral", "negative"]
    topic_keywords: list[str] = Field(default_factory=list)


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    )


def _format_evidence(documents: list[dict[str, Any]]) -> str:
    blocks = []
    for index, doc in enumerate(documents, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] chunk_id: {doc.get('chunk_id')}",
                    f"title: {doc.get('title') or 'untitled'}",
                    f"source_type: {doc.get('source_type') or 'unknown'}",
                    f"category: {doc.get('category') or 'unknown'}",
                    f"score: {doc.get('score')}",
                    f"content: {' '.join(str(doc.get('chunk_text') or '').split())}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _answer_with_evidence(*, system_prompt: str, query_text: str, documents: list[dict[str, Any]]) -> str:
    response = _llm().invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"Customer question:\n{query_text}\n\n"
                    f"Evidence documents:\n{_format_evidence(documents)}\n\n"
                    "Write a concise, polite Korean customer-facing answer."
                )
            ),
        ]
    )
    return str(response.content).strip()


def _compact_row(row: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in row.items() if value is not None)


def _context_rows_to_evidence(rows: list[dict[str, Any]], *, source_type: str, category: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        doc_id = (
            row.get("chunk_id")
            or row.get("documents_id")
            or row.get("payment_id")
            or row.get("refund_id")
            or row.get("delivery_id")
            or row.get("gacha_id")
            or row.get("insight_id")
            or rank
        )
        evidence.append(
            {
                "chunk_id": str(doc_id),
                "document_id": str(doc_id),
                "source_type": row.get("source_type") or source_type,
                "category": row.get("category") or category,
                "title": row.get("title") or f"{source_type} evidence",
                "chunk_text": row.get("chunk_text") or row.get("raw_content") or _compact_row(row),
                "score": float(row.get("score") or 1.0),
                "retrieval_rank": rank,
            }
        )
    return evidence


def _collect_user_context(user_id: int, account_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
    account_filter = "AND (%s IS NULL OR a.account_id = %s)"
    account_params = (account_id, account_id)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT a.account_id, a.user_id, a.game_name, a.uid, a.server_region, a.account_status
                FROM game_accounts a
                WHERE a.user_id = %s {account_filter}
                ORDER BY a.account_id
                LIMIT 10
                """,
                (user_id, *account_params),
            )
            accounts = [dict(row) for row in cur.fetchall()]
            cur.execute(
                f"""
                SELECT p.payment_id, p.account_id, p.product_name, p.product_type, p.amount, p.currency,
                       p.payment_method, p.payment_status, p.transaction_id, p.paid_at
                FROM payments p
                JOIN game_accounts a ON a.account_id = p.account_id
                WHERE a.user_id = %s {account_filter}
                ORDER BY p.paid_at DESC NULLS LAST
                LIMIT 10
                """,
                (user_id, *account_params),
            )
            payments = [dict(row) for row in cur.fetchall()]
            cur.execute(
                f"""
                SELECT r.refund_id, r.payment_id, p.account_id, p.product_name, p.payment_status, p.paid_at,
                       r.refund_status, r.refund_reason, r.requested_at, r.processed_at
                FROM refunds r
                JOIN payments p ON p.payment_id = r.payment_id
                JOIN game_accounts a ON a.account_id = p.account_id
                WHERE a.user_id = %s {account_filter}
                ORDER BY r.requested_at DESC NULLS LAST
                LIMIT 10
                """,
                (user_id, *account_params),
            )
            refunds = [dict(row) for row in cur.fetchall()]
            cur.execute(
                f"""
                SELECT d.delivery_id, d.payment_id, d.account_id, d.source_type, d.item_name, d.quantity,
                       d.delivery_status, d.expected_at, d.delivered_at
                FROM item_delivery_logs d
                JOIN game_accounts a ON a.account_id = d.account_id
                WHERE a.user_id = %s {account_filter}
                ORDER BY d.expected_at DESC NULLS LAST, d.delivered_at DESC NULLS LAST
                LIMIT 10
                """,
                (user_id, *account_params),
            )
            item_delivery_logs = [dict(row) for row in cur.fetchall()]
            cur.execute(
                f"""
                SELECT g.gacha_id, g.account_id, g.banner_name, g.item_name, g.item_type, g.rarity,
                       g.pity_count, g.pulled_at
                FROM gacha_logs g
                JOIN game_accounts a ON a.account_id = g.account_id
                WHERE a.user_id = %s {account_filter}
                ORDER BY g.pulled_at DESC NULLS LAST
                LIMIT 10
                """,
                (user_id, *account_params),
            )
            gacha_logs = [dict(row) for row in cur.fetchall()]
    return {
        "accounts": accounts,
        "payments": payments,
        "refunds": refunds,
        "item_delivery_logs": item_delivery_logs,
        "gacha_logs": gacha_logs,
    }


def collect_payment_context_by_user(user_id: int, account_id: int | None = None) -> dict[str, Any]:
    """Read payment-related evidence only from accounts owned by the logged-in user."""
    data = _collect_user_context(user_id, account_id)
    counts = {key: len(rows) for key, rows in data.items() if key != "accounts" and rows}
    return {
        "status": "ok",
        "user_id": user_id,
        "account_id": account_id,
        "data": data,
        "counts": counts,
        "count": sum(counts.values()),
    }


def collect_route_evidence(request: SharedDraftRequest) -> list[dict[str, Any]]:
    if request.category == "faq":
        return []
    if request.context_rows:
        source_type = "payment_context" if request.category == "payment" else f"{request.category}_context"
        category = "결제" if request.category == "payment" else ("VOC" if request.category == "voc" else "인게임/버그")
        return _context_rows_to_evidence(request.context_rows, source_type=source_type, category=category)
    if request.user_id is None:
        return list(request.retrieved_documents)

    context = _collect_user_context(request.user_id, request.account_id)
    if request.category == "payment":
        rows = context["payments"] + context["refunds"] + context["item_delivery_logs"] + context["gacha_logs"]
        return _context_rows_to_evidence(rows, source_type="payment_context", category="결제")
    if request.category == "bug":
        rows = context["item_delivery_logs"] + context["gacha_logs"]
        return _context_rows_to_evidence(rows, source_type="bug_context", category="인게임/버그")
    return list(request.retrieved_documents)


def _run_payment_draft(request: SharedDraftRequest) -> SharedDraftResult:
    documents = collect_route_evidence(request)
    if not documents:
        return SharedDraftResult(
            draft_text=PAYMENT_FALLBACK_RESPONSE,
            reasoning_node="payment_agent",
            review_required=True or request.force_review,
            metadata={"failure_reason": "missing_payment_evidence"},
        )
    answer = _answer_with_evidence(system_prompt=PAYMENT_SYSTEM_PROMPT, query_text=request.query_text, documents=documents)
    return SharedDraftResult(
        draft_text=answer,
        reasoning_node="payment_agent",
        retrieved_documents=documents,
        evidence_doc_ids=[str(doc["chunk_id"]) for doc in documents],
        review_required=request.force_review,
    )


def _run_bug_draft(request: SharedDraftRequest) -> SharedDraftResult:
    documents = collect_route_evidence(request) or list(request.retrieved_documents)
    if not documents:
        return SharedDraftResult(
            draft_text=BUG_FALLBACK_RESPONSE,
            reasoning_node="bug_agent",
            review_required=True,
            metadata={"failure_reason": "missing_bug_evidence"},
        )
    answer = _answer_with_evidence(system_prompt=BUG_SYSTEM_PROMPT, query_text=request.query_text, documents=documents)
    return SharedDraftResult(
        draft_text=answer,
        reasoning_node="bug_agent",
        retrieved_documents=documents,
        evidence_doc_ids=[str(doc["chunk_id"]) for doc in documents],
        review_required=request.force_review,
    )


def _rerank_documents(documents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    reranked_json = rerank_documents.invoke(
        {
            "docs_json": json.dumps(documents, ensure_ascii=False),
            "query": query,
        }
    )
    return json.loads(reranked_json)


def _run_faq_draft(request: SharedDraftRequest) -> SharedDraftResult:
    if request.is_actionable is False or request.should_use_rag is False:
        return SharedDraftResult(
            draft_text=SAFE_FALLBACK_RESPONSE,
            reasoning_node="faq_agent",
            review_required=True or request.force_review,
            metadata={"failure_reason": request.fallback_reason or "rag_not_requested"},
        )

    enriched = enrich_retrieval_query(request.query_text)
    retrieval_query = enriched.query_text
    if not retrieval_query:
        return SharedDraftResult(
            draft_text=SAFE_FALLBACK_RESPONSE,
            reasoning_node="faq_agent",
            review_required=True,
            metadata={"failure_reason": "empty_retrieval_query"},
        )
    embedding_json = embed_query.invoke({"text": retrieval_query})
    final_top_k = int(os.environ.get("FAQ_RETRIEVAL_TOP_K", os.environ.get("RETRIEVAL_TOP_K", "3")))
    candidate_top_k = max(int(os.environ.get("FAQ_RERANK_CANDIDATE_TOP_K", "10")), final_top_k)
    documents = search_document_chunks(
        embedding_json=embedding_json,
        query_text=retrieval_query,
        top_k=candidate_top_k,
        prefer_faq=True,
        enrichment=enriched,
    )
    documents = _rerank_documents(documents, retrieval_query)[:final_top_k]
    if not documents:
        return SharedDraftResult(
            draft_text=SAFE_FALLBACK_RESPONSE,
            reasoning_node="faq_agent",
            review_required=True,
            metadata={
                "retrieval_query": retrieval_query,
                "retrieval_enrichment": enriched.model_dump(),
                "failure_reason": "no_retrieved_documents",
            },
        )
    answer = _answer_with_evidence(system_prompt=FAQ_SYSTEM_PROMPT, query_text=request.query_text, documents=documents)
    return SharedDraftResult(
        draft_text=answer,
        reasoning_node="faq_agent",
        retrieved_documents=documents,
        evidence_doc_ids=[str(doc["chunk_id"]) for doc in documents],
        review_required=request.force_review,
        metadata={
            "retrieval_query": retrieval_query,
            "retrieval_enrichment": enriched.model_dump(),
            "faq_failure_reason": None,
        },
    )


def _classify_voc(text: str) -> VocClassification:
    classifier = _llm().with_structured_output(VocClassification)
    return classifier.invoke(
        [
            SystemMessage(
                content=(
                    "You classify Korean game customer feedback into VOC fields. "
                    "voc_type must be one of suggestion, complaint, praise, multi_intent, other. "
                    "sentiment must be one of positive, neutral, negative. "
                    "topic_keywords must contain 2 to 5 normalized Korean noun keywords."
                )
            ),
            HumanMessage(content=f"Classify this VOC.\ncontent: {text}"),
        ]
    )


def _build_voc_response(voc_type: str) -> str:
    responses = {
        "complaint": "불편을 겪으신 점 확인했습니다. 관련 부서에서 내용과 발생 상황을 검토할 수 있도록 접수하겠습니다.",
        "suggestion": "좋은 제안 감사합니다. 보내주신 개선 의견은 관련 부서에 전달하여 검토할 수 있도록 접수하겠습니다.",
        "praise": "따뜻한 의견 감사합니다. 보내주신 내용은 관련 담당자에게 전달하겠습니다.",
        "multi_intent": "여러 의견을 함께 보내주셔서 감사합니다. 각 항목별로 확인할 수 있도록 접수하겠습니다.",
        "other": VOC_FIXED_RESPONSE,
    }
    return responses[voc_type]


def _run_voc_draft(request: SharedDraftRequest) -> SharedDraftResult:
    if request.is_actionable is False and request.should_use_rag is False:
        voc_type = "other"
        sentiment = "negative"
        topic_keywords: list[str] = []
        answer = VOC_FIXED_RESPONSE
    else:
        classification = _classify_voc(request.query_text)
        voc_type = classification.voc_type
        sentiment = classification.sentiment
        topic_keywords = classification.topic_keywords
        answer = _build_voc_response(voc_type)
    evidence = [
        {
            "chunk_id": f"voc_template:{voc_type}",
            "document_id": voc_type,
            "source_type": "voc_template",
            "category": "VOC",
            "title": "VOC template",
            "chunk_text": f"VOC template response: {voc_type}",
            "score": 1.0,
            "retrieval_rank": 1,
        }
    ]
    return SharedDraftResult(
        draft_text=answer,
        reasoning_node="voc_agent",
        retrieved_documents=evidence,
        evidence_doc_ids=[evidence[0]["chunk_id"]],
        review_required=request.force_review,
        metadata={
            "voc_type": voc_type,
            "sentiment": sentiment,
            "topic_keywords": topic_keywords,
        },
    )


def generate_shared_draft(request: SharedDraftRequest) -> SharedDraftResult:
    if request.category == "payment":
        return _run_payment_draft(request)
    if request.category == "bug":
        return _run_bug_draft(request)
    if request.category == "faq":
        return _run_faq_draft(request)
    return _run_voc_draft(request)
