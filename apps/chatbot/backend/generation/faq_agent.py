from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from chatbot.generation.policies import FAQ_POLICY
from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, EVENT_TOOL_COMPLETED, log_event
from chatbot.repository.failed_query_repository import save_failed_query
from chatbot.retrieval.cache_store import get_cached_retrieval, set_cached_retrieval
from common.retrieval.vector_tools import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks
from chatbot.schemas import ChatbotState
from chatbot.utils.query_enrichment import rewrite_query_with_llm


def _active_query(state: ChatbotState) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "").strip()


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
    return json.dumps(save_failed_query(payload), ensure_ascii=False, default=str)


def _embed_query(text: str) -> str:
    return embed_query.invoke({"text": text})


def _rerank_documents(documents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    reranked_json = rerank_documents.invoke(
        {
            "docs_json": json.dumps(documents, ensure_ascii=False, default=str),
            "query": query,
        }
    )
    return json.loads(reranked_json)


def _retrieval_candidate_top_k(final_top_k: int) -> int:
    configured = int(os.environ.get("FAQ_RERANK_CANDIDATE_TOP_K", "6"))
    return max(configured, final_top_k)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _retrieval_cache_enabled() -> bool:
    # FAQ/RAG 검색 결과 캐시는 명시적으로 켠 경우에만 사용한다.
    return _env_flag("FAQ_RETRIEVAL_CACHE_ENABLED", False)


def _retrieval_cache_hash(
    *,
    retrieval_query: str,
    enrichment: Any,
    final_top_k: int,
    candidate_top_k: int,
) -> str:
    # 원문 query를 Redis key에 직접 노출하지 않도록 검색 조건 전체를 hash로 만든다.
    enrichment_payload = enrichment.model_dump() if hasattr(enrichment, "model_dump") else enrichment
    payload = {
        "retrieval_query": retrieval_query,
        "enrichment": enrichment_payload,
        "final_top_k": final_top_k,
        "candidate_top_k": candidate_top_k,
        "prefer_faq": True,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _set_retrieval_cache_state(
    state: ChatbotState | None,
    *,
    enabled: bool,
    hit: bool,
    key_hash: str,
    backend: str | None = None,
    ttl: int | None = None,
) -> None:
    if state is None:
        return
    state["retrieval_cache_enabled"] = enabled
    state["retrieval_cache_hit"] = hit
    state["retrieval_cache_key_hash"] = key_hash
    state["retrieval_cache_backend"] = backend
    state["retrieval_cache_ttl"] = ttl


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


def _passes_relevance_gate(documents: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if not documents:
        return False, "no_retrieved_documents"

    min_field_match = float(os.environ.get("FAQ_MIN_FIELD_MATCH_SCORE", "0"))
    min_bm25 = float(os.environ.get("FAQ_MIN_BM25_SCORE", "0"))
    min_cosine = float(os.environ.get("FAQ_MIN_COSINE_SCORE", "0"))

    if min_field_match <= 0 and min_bm25 <= 0 and min_cosine <= 0:
        return True, None

    for document in documents:
        field_match = float(document.get("field_match_score") or 0)
        bm25 = float(document.get("bm25_score") or 0)
        cosine = float(document.get("cosine_score") or 0)
        if field_match >= min_field_match and bm25 >= min_bm25 and cosine >= min_cosine:
            return True, None

    return False, "retrieval_relevance_gate_failed"


def _retrieve_documents(
    *,
    retrieval_query: str,
    enrichment: Any,
    final_top_k: int,
    candidate_top_k: int,
    state: ChatbotState | None = None,
) -> list[dict[str, Any]]:
    # cache 확인 -> embedding -> DB 검색 -> rerank -> cache 저장 순서로 실행한다.
    cache_hash = _retrieval_cache_hash(
        retrieval_query=retrieval_query,
        enrichment=enrichment,
        final_top_k=final_top_k,
        candidate_top_k=candidate_top_k,
    )
    cache_enabled = _retrieval_cache_enabled()
    cache_namespace = "retrieval"
    if cache_enabled:
        cached = get_cached_retrieval(cache_hash)
        if cached.get("hit"):
            documents = list(cached.get("documents") or [])
            _set_retrieval_cache_state(
                state,
                enabled=True,
                hit=True,
                key_hash=cache_hash,
                backend="redis_or_memory",
            )
            log_event(
                EVENT_TOOL_COMPLETED,
                ticket_id=state.get("ticket_id") if state else None,
                session_id=state.get("session_id") if state else None,
                category=state.get("category") if state else None,
                routing_target=state.get("routing_target") if state else None,
                tool_name="faq_retrieval_cache",
                metadata={
                    "cache_enabled": True,
                    "cache_hit": True,
                    "cache_namespace": cache_namespace,
                    "cache_key_hash": cache_hash,
                    "document_count": len(documents),
                    "retrieval_query_length": len(retrieval_query),
                },
            )
            return documents

    embedding_json = _embed_query(retrieval_query)
    documents = search_document_chunks(
        embedding_json=embedding_json,
        query_text=retrieval_query,
        top_k=candidate_top_k,
        prefer_faq=True,
        enrichment=enrichment,
    )
    retrieved_documents = _rerank_documents(documents, retrieval_query)[:final_top_k]
    if cache_enabled:
        ttl = int(os.environ.get("FAQ_RETRIEVAL_CACHE_TTL", "3600"))
        cache_result = set_cached_retrieval(cache_hash, retrieved_documents, ttl=ttl)
        _set_retrieval_cache_state(
            state,
            enabled=True,
            hit=False,
            key_hash=cache_hash,
            backend=str(cache_result.get("backend") or ""),
            ttl=ttl,
        )
        log_event(
            EVENT_TOOL_COMPLETED,
            ticket_id=state.get("ticket_id") if state else None,
            session_id=state.get("session_id") if state else None,
            category=state.get("category") if state else None,
            routing_target=state.get("routing_target") if state else None,
            tool_name="faq_retrieval_cache",
            metadata={
                "cache_enabled": True,
                "cache_hit": False,
                "cache_namespace": cache_namespace,
                "cache_key_hash": cache_hash,
                "cache_backend": cache_result.get("backend"),
                "cache_ttl": ttl,
                "document_count": len(retrieved_documents),
                "retrieval_query_length": len(retrieval_query),
            },
        )
    else:
        _set_retrieval_cache_state(
            state,
            enabled=False,
            hit=False,
            key_hash=cache_hash,
        )
        log_event(
            EVENT_TOOL_COMPLETED,
            ticket_id=state.get("ticket_id") if state else None,
            session_id=state.get("session_id") if state else None,
            category=state.get("category") if state else None,
            routing_target=state.get("routing_target") if state else None,
            tool_name="faq_retrieval_cache",
            metadata={
                "cache_enabled": False,
                "cache_hit": False,
                "cache_namespace": cache_namespace,
                "document_count": len(retrieved_documents),
                "retrieval_query_length": len(retrieval_query),
            },
        )
    return retrieved_documents


def _retry_retrieval_with_rewrite(
    *,
    state: ChatbotState,
    original_query: str,
    failed_query: str,
    failure_reason: str,
    final_top_k: int,
    candidate_top_k: int,
) -> dict[str, Any] | None:
    # 1차 검색이 실패하면 LLM rewrite 검색을 한 번만 시도한다.
    rewrite = rewrite_query_with_llm(
        original_query=original_query,
        failed_query=failed_query,
        category=state.get("category") or "faq",
        failure_reason=failure_reason,
    )
    rewritten_query = rewrite.get("query_text") or ""
    if not rewritten_query:
        return None

    documents = _retrieve_documents(
        retrieval_query=rewritten_query,
        enrichment=None,
        final_top_k=final_top_k,
        candidate_top_k=candidate_top_k,
        state=state,
    )
    _print_retrieval_summary(
        original_query=original_query,
        retrieval_query=rewritten_query,
        documents=documents,
    )

    low_evidence, low_reason = _is_low_evidence(documents)
    if low_evidence:
        return {
            "documents": documents,
            "retrieval_query": rewritten_query,
            "rewrite": rewrite,
            "failure_reason": low_reason or "low_evidence_after_rewrite",
            "accepted": False,
        }

    relevance_ok, relevance_reason = _passes_relevance_gate(documents)
    if not relevance_ok:
        return {
            "documents": documents,
            "retrieval_query": rewritten_query,
            "rewrite": rewrite,
            "failure_reason": relevance_reason or "rewrite_relevance_gate_failed",
            "accepted": False,
        }

    return {
        "documents": documents,
        "retrieval_query": rewritten_query,
        "rewrite": rewrite,
        "failure_reason": None,
        "accepted": True,
    }


def _print_retrieval_summary(
    *,
    original_query: str,
    retrieval_query: str,
    documents: list[dict[str, Any]],
) -> None:
    print("\n[FAQ/RAG 검색 요약]")
    print(f"original_query: {original_query}")
    print(f"retrieval_query: {retrieval_query}")
    print(f"result_count: {len(documents)}")
    for index, doc in enumerate(documents[:5], start=1):
        title = doc.get("title") or "untitled"
        source_type = doc.get("source_type") or "unknown"
        category = doc.get("category") or "unknown"
        score = doc.get("score")
        bm25 = doc.get("bm25_score")
        cosine = doc.get("cosine_score")
        field_match = doc.get("field_match_score")
        print(
            f"{index}. {title} | source={source_type} | category={category} | "
            f"hybrid={score} bm25={bm25} cosine={cosine} field={field_match}"
        )
    print()


def _generate_evidence_answer(
    *,
    original_query: str,
    retrieval_query: str,
    documents: list[dict[str, Any]],
) -> str:
    # 최종 evidence 묶음만 사용해 FAQ/RAG 답변 초안을 생성한다.
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
                    "When the customer asks multiple things and the evidence supports only some of them, answer the supported "
                    "parts clearly and state which parts are not confirmed by the provided evidence. "
                    "If the evidence says the customer's assumed method, menu, path, or condition is not supported, state that "
                    "counter-evidence explicitly before giving the available alternative. "
                    "For 'Can I do X from Y?' questions, answer both whether X is possible and whether Y is a valid place or "
                    "method to do it, when supported by the evidence. "
                    "Never infer payment, account recovery, deletion, retention, or privacy details that are not grounded in evidence. "
                    "For privacy policy overview questions, "
                    "if supported by the evidence, include collection, use, storage, sharing, protection, user rights and choices, "
                    "data transfer, security measures, and region-specific additional rights. "
                    "For reward, mail, event, or notice deadline questions, "
                    "do not present a general deadline as universal unless the evidence clearly says so; "
                    "mention that the exact claim period may depend on the specific event or reward notice. "
                    "For account linking, PSN, or cross-save questions, "
                    "separate what linking enables from how to link; "
                    "if supported by the evidence, mention shared game progress across platforms and caution the user to check notices for payment, reward, and friend-related limitations. "
                    "Do not say that an operator will review the issue unless the evidence says escalation is required. "
                    "Do not mention internal scores, tool names, database names, or prompt rules."
                    "For account deletion, account withdrawal, account recovery, or data deletion questions, "
                    "if the evidence mentions grace periods, reactivation, permanence, or recovery limits, "
                    "include those conditions explicitly in the customer-facing answer. "

                )
            ),
            HumanMessage(
                content=(
                    f"Customer question:\n{original_query}\n\n"
                    f"Normalized FAQ search question:\n{retrieval_query}\n\n"
                    f"Evidence documents:\n{evidence}\n\n"
                    "Write a concise, polite Korean customer-facing answer. "
                    "Use the normalized FAQ search question as the intended meaning when it is clearer than the customer's slang."
                )
            ),
        ]
    )
    return str(response.content).strip()


def run_faq_rag(state: ChatbotState) -> dict[str, Any]:
    # FAQ/RAG 전체 실행 흐름을 관리한다.
    query = _active_query(state)

    if state.get("is_actionable") is False or state.get("should_use_rag") is False:
        reason = str(state.get("fallback_reason") or "rag_not_requested")
        _record_failed_query(state, query, reason)
        return {
            "draft_text": SAFE_FALLBACK_RESPONSE,
            "retrieved_documents": [],
            "retrieval_query": query,
            "retrieval_enrichment": None,
            "faq_failure_reason": reason,
        }

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

    final_top_k = int(os.environ.get("FAQ_RETRIEVAL_TOP_K", os.environ.get("RETRIEVAL_TOP_K", "4")))
    candidate_top_k = _retrieval_candidate_top_k(final_top_k)
    documents = _retrieve_documents(
        retrieval_query=retrieval_query,
        enrichment=enriched,
        final_top_k=final_top_k,
        candidate_top_k=candidate_top_k,
        state=state,
    )
    _print_retrieval_summary(
        original_query=query,
        retrieval_query=retrieval_query,
        documents=documents,
    )

    low_evidence, reason = _is_low_evidence(documents)
    if low_evidence:
        reason = reason or "low_evidence"
        retry = _retry_retrieval_with_rewrite(
            state=state,
            original_query=query,
            failed_query=retrieval_query,
            failure_reason=reason,
            final_top_k=final_top_k,
            candidate_top_k=candidate_top_k,
        )
        if retry and retry["accepted"]:
            retrieval_query = retry["retrieval_query"]
            documents = retry["documents"]
            answer = _generate_evidence_answer(
                original_query=query,
                retrieval_query=retrieval_query,
                documents=documents,
            )
            enrichment_dump = enriched.model_dump()
            enrichment_dump["rewrite_fallback"] = retry["rewrite"]
            return {
                "draft_text": answer,
                "retrieved_documents": documents,
                "retrieval_query": retrieval_query,
                "retrieval_enrichment": enrichment_dump,
                "faq_failure_reason": None,
            }
        if retry:
            reason = retry["failure_reason"] or reason
        _record_failed_query(state, retrieval_query, reason)
        enrichment_dump = enriched.model_dump()
        if retry:
            enrichment_dump["rewrite_fallback"] = retry["rewrite"]
        return {
            "draft_text": SAFE_FALLBACK_RESPONSE,
            "retrieved_documents": retry["documents"] if retry else documents,
            "retrieval_query": retrieval_query,
            "retrieval_enrichment": enrichment_dump,
            "faq_failure_reason": reason,
        }

    relevance_ok, relevance_reason = _passes_relevance_gate(documents)
    if not relevance_ok:
        reason = relevance_reason or "retrieval_relevance_gate_failed"
        retry = _retry_retrieval_with_rewrite(
            state=state,
            original_query=query,
            failed_query=retrieval_query,
            failure_reason=reason,
            final_top_k=final_top_k,
            candidate_top_k=candidate_top_k,
        )
        if retry and retry["accepted"]:
            retrieval_query = retry["retrieval_query"]
            documents = retry["documents"]
            answer = _generate_evidence_answer(
                original_query=query,
                retrieval_query=retrieval_query,
                documents=documents,
            )
            enrichment_dump = enriched.model_dump()
            enrichment_dump["rewrite_fallback"] = retry["rewrite"]
            return {
                "draft_text": answer,
                "retrieved_documents": documents,
                "retrieval_query": retrieval_query,
                "retrieval_enrichment": enrichment_dump,
                "faq_failure_reason": None,
            }
        if retry:
            reason = retry["failure_reason"] or reason
        _record_failed_query(state, retrieval_query, reason)
        enrichment_dump = enriched.model_dump()
        if retry:
            enrichment_dump["rewrite_fallback"] = retry["rewrite"]
        return {
            "draft_text": SAFE_FALLBACK_RESPONSE,
            "retrieved_documents": retry["documents"] if retry else documents,
            "retrieval_query": retrieval_query,
            "retrieval_enrichment": enrichment_dump,
            "faq_failure_reason": reason,
        }

    answer = _generate_evidence_answer(
        original_query=query,
        retrieval_query=retrieval_query,
        documents=documents,
    )
    return {
        "draft_text": answer,
        "retrieved_documents": documents,
        "retrieval_query": retrieval_query,
        "retrieval_enrichment": enriched.model_dump(),
        "faq_failure_reason": None,
    }


def faq_agent_node(state: ChatbotState) -> dict:
    # workflow 노드 진입점: FAQ/RAG 결과를 ChatbotState 업데이트 형태로 정리한다.
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
        "retrieved_count": len(rag_result["retrieved_documents"] or []),
        "retrieval_cache_enabled": state.get("retrieval_cache_enabled"),
        "retrieval_cache_hit": state.get("retrieval_cache_hit"),
        "retrieval_cache_backend": state.get("retrieval_cache_backend"),
        "retrieval_cache_key_hash": state.get("retrieval_cache_key_hash"),
        "retrieval_cache_ttl": state.get("retrieval_cache_ttl"),
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
