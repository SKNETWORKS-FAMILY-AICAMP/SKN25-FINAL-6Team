from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from chatbot.generation.policies import FAQ_POLICY
from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.retrieval.vector_tools import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_failed_query


def _active_query(state: ChatbotState) -> str:
    return str(state.get("enriched_query") or state.get("raw_query") or "").strip()


def _format_evidence(documents: list[dict[str, Any]]) -> str:
    blocks = []
    for index, doc in enumerate(documents, start=1):
        title = doc.get("title") or "untitled"
        source_type = doc.get("source_type") or "unknown"
        category = doc.get("category") or "unknown"
        chunk_text = " ".join(str(doc.get("chunk_text") or "").split())
        blocks.append(
            "\n".join(
                [
                    f"[{index}] title: {title}",
                    f"source_type: {source_type}",
                    f"category: {category}",
                    f"score: {doc.get('score')}",
                    f"content: {chunk_text}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _record_failed_query(state: ChatbotState, query: str, reason: str) -> None:
    ticket_id = state.get("ticket_id")
    if ticket_id is None:
        return
    _write_failed_query(
        {
            "ticket_id": ticket_id,
            "query": query,
            "category": state.get("category") or "FAQ",
            "reason": reason,
        }
    )


def _write_failed_query(payload: dict[str, Any]) -> str:
    return write_failed_query.invoke({"payload": payload})


def _embed_query(text: str) -> str:
    return embed_query.invoke({"text": text})


def _rerank_documents(documents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    reranked_json = rerank_documents.invoke(
        {
            "docs_json": json.dumps(documents, ensure_ascii=False),
            "query": query,
        }
    )
    return json.loads(reranked_json)


def _is_low_evidence(documents: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if not documents:
        return True, "no_retrieved_documents"
    if not any(str(doc.get("chunk_text") or "").strip() for doc in documents):
        return True, "empty_retrieved_documents"

    min_score = float(os.environ.get("FAQ_MIN_RRF_SCORE", "0"))
    if min_score > 0:
        best_score = max(float(doc.get("score") or 0) for doc in documents)
        if best_score < min_score:
            return True, f"low_retrieval_score:{best_score:.6f}"

    return False, None


def _generate_evidence_answer(query: str, documents: list[dict[str, Any]]) -> str:
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        raise RuntimeError("OpenAI settings are missing.")

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    )
    evidence = _format_evidence(documents)
    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "You are a Korean game customer support FAQ/RAG drafting unit. "
                    "Answer only with facts supported by the provided evidence. "
                    "Do not use adjacent maintenance, outage, or incident notices as an answer to a how-to question "
                    "unless the customer explicitly asked about maintenance, outage, or incidents. "
                    "If the evidence does not explicitly answer the requested topic, say that exact guidance is not available "
                    "and avoid adding unrelated operational notices. "
                    "Do not say that an operator will review the issue unless the evidence says escalation is required. "
                    "Do not mention internal scores, tool names, database names, or prompt rules."
                )
            ),
            HumanMessage(
                content=(
                    f"Customer question:\n{query}\n\n"
                    f"Evidence documents:\n{evidence}\n\n"
                    "Write a concise, polite Korean customer-facing answer."
                )
            ),
        ]
    )
    return str(response.content).strip()


def run_faq_rag(state: ChatbotState) -> dict[str, Any]:
    """Run deterministic FAQ/RAG: refine, embed, search, rerank, then answer once."""
    query = _active_query(state)
    enriched = enrich_retrieval_query(query)
    retrieval_query = enriched.query_text
    if not retrieval_query:
        _record_failed_query(state, query, "empty_retrieval_query")
        return {
            "draft_text": SAFE_FALLBACK_RESPONSE,
            "retrieved_documents": [],
            "retrieval_query": retrieval_query,
            "retrieval_enrichment": enriched.model_dump(),
            "faq_failure_reason": "empty_retrieval_query",
        }

    embedding_json = _embed_query(retrieval_query)
    documents = search_document_chunks(
        embedding_json=embedding_json,
        query_text=retrieval_query,
        top_k=int(os.environ.get("FAQ_RETRIEVAL_TOP_K", os.environ.get("RETRIEVAL_TOP_K", "5"))),
        prefer_faq=True,
        enrichment=enriched,
    )
    documents = _rerank_documents(documents, retrieval_query)

    low_evidence, reason = _is_low_evidence(documents)
    if low_evidence:
        reason = reason or "low_evidence"
        _record_failed_query(state, retrieval_query, reason)
        return {
            "draft_text": SAFE_FALLBACK_RESPONSE,
            "retrieved_documents": documents,
            "retrieval_query": retrieval_query,
            "retrieval_enrichment": enriched.model_dump(),
            "faq_failure_reason": reason,
        }

    answer = _generate_evidence_answer(query, documents)
    return {
        "draft_text": answer,
        "retrieved_documents": documents,
        "retrieval_query": retrieval_query,
        "retrieval_enrichment": enriched.model_dump(),
        "faq_failure_reason": None,
    }


def faq_agent_node(state: ChatbotState) -> dict:
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=FAQ_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    rag_result = run_faq_rag(state)
    update = {
        "draft_text": rag_result["draft_text"],
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": FAQ_POLICY.name,
        "retrieval_query": rag_result["retrieval_query"],
        "retrieval_enrichment": rag_result.get("retrieval_enrichment"),
        "retrieved_documents": rag_result["retrieved_documents"],
        "faq_failure_reason": rag_result["faq_failure_reason"],
    }
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=FAQ_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={
            "draft_length": len(update.get("draft_text") or ""),
            "retrieved_count": len(update.get("retrieved_documents") or []),
            "failure_reason": update.get("faq_failure_reason"),
        },
    )
    return update
