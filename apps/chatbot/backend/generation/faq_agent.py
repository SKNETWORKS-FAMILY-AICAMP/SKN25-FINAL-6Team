from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from chatbot.generation.policies import FAQ_POLICY
from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, EVENT_TOOL_COMPLETED, log_event
from chatbot.retrieval.cache_store import get_cached_retrieval, set_cached_retrieval
from common.retrieval.vector_tools import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_failed_query
from chatbot.utils.query_enrichment import rewrite_query_with_llm


class MultihopQueryPlan(BaseModel):
    """Structured decision for conditional FAQ multi-hop retrieval."""

    needs_multihop: bool = Field(description="Whether additional retrieval queries are needed.")
    search_queries: list[str] = Field(
        default_factory=list,
        description="Additional concise Korean FAQ/RAG search queries.",
    )
    reason: str = Field(default="", description="Short reason for the decomposition decision.")


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
    return write_failed_query.invoke({"payload": payload})


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
    """Allow retrieval caching only when explicitly enabled for FAQ/RAG."""
    return _env_flag("FAQ_RETRIEVAL_CACHE_ENABLED", False)


def _multihop_enabled() -> bool:
    return _env_flag("FAQ_MULTIHOP_ENABLED", True)


def _multihop_precheck_enabled() -> bool:
    return _env_flag("FAQ_MULTIHOP_PRECHECK_ENABLED", True)


def _retrieval_cache_hash(
    *,
    retrieval_query: str,
    enrichment: Any,
    final_top_k: int,
    candidate_top_k: int,
) -> str:
    """Hash retrieval inputs without storing the raw query in Redis keys."""
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


def _passes_multihop_relevance_gate(documents: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if not documents:
        return False, "no_retrieved_documents"

    min_field_match = float(
        os.environ.get(
            "FAQ_MULTIHOP_MIN_FIELD_MATCH_SCORE",
            os.environ.get("FAQ_MIN_FIELD_MATCH_SCORE", "0"),
        )
    )
    if min_field_match <= 0:
        return True, None

    for document in documents:
        if float(document.get("field_match_score") or 0) >= min_field_match:
            return True, None

    return False, "multihop_relevance_gate_failed"


def _multihop_evidence_summary(documents: list[dict[str, Any]], max_documents: int = 4) -> list[dict[str, str]]:
    summary = []
    for document in documents[:max_documents]:
        summary.append(
            {
                "title": str(document.get("title") or ""),
                "source_type": str(document.get("source_type") or ""),
                "category": str(document.get("category") or ""),
                "content": " ".join(str(document.get("chunk_text") or "").split())[:500],
            }
        )
    return summary


_MULTIHOP_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "account_deletion": ("계정 삭제", "계정을 삭제", "탈퇴", "삭제 신청"),
    "payment": ("결제", "구매", "결제 기록", "결제 내역", "충전"),
    "refund": ("환불", "취소", "회수"),
    "privacy": ("개인정보", "처리방침", "보관", "제3자", "수집"),
    "recovery": ("복구", "되돌", "나중에", "다시"),
    "linking": ("연동", "PSN", "크로스 세이브", "플랫폼"),
    "game_data": ("게임 데이터", "진행도", "UID", "세이브"),
    "reward_rule": ("보상 조건", "수령 조건", "대상", "초회", "초회 충전", "초회충전", "공월 축복"),
    "reward_delivery": ("보상", "보너스", "우편함", "지급", "미지급", "못 받", "안 들어", "수령", "받을"),
}


def _looks_like_multihop_query(text: str) -> tuple[bool, str]:
    """Cheaply skip the planner for simple FAQ questions."""
    if not _multihop_precheck_enabled():
        return True, "precheck_disabled"

    normalized = f" {' '.join(str(text or '').split())} "
    matched_domains = {
        domain
        for domain, keywords in _MULTIHOP_DOMAIN_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    }
    if len(matched_domains) < 2:
        return False, "single_domain_query"

    if {"account_deletion", "payment"}.issubset(matched_domains):
        return True, "account_deletion_with_payment"
    if {"account_deletion", "privacy"}.issubset(matched_domains):
        return True, "account_deletion_with_privacy"
    if {"account_deletion", "recovery"}.issubset(matched_domains):
        return True, "account_deletion_with_recovery"
    if {"privacy", "recovery"}.issubset(matched_domains):
        return True, "privacy_with_recovery"
    if {"payment", "refund"}.issubset(matched_domains):
        return True, "payment_with_refund"
    if {"payment", "reward_delivery"}.issubset(matched_domains):
        return True, "payment_with_reward_delivery"
    if {"linking", "game_data"}.issubset(matched_domains) and any(
        keyword in normalized for keyword in ("해제", "사라", "삭제", "보존")
    ):
        return True, "linking_with_game_data_loss"
    if {"reward_rule", "reward_delivery"}.issubset(matched_domains) and any(
        keyword in normalized for keyword in ("나중에", "이미 산", "다시", "초기화", "보관 기간", "조건")
    ):
        return True, "reward_rule_with_delivery_exception"

    return False, "no_multihop_pattern"


def _decompose_multihop_queries(
    *,
    original_query: str,
    retrieval_query: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build additional retrieval queries for compound FAQ questions."""
    if not _multihop_enabled():
        return {"queries": [], "reason": "multihop_disabled"}

    precheck_ok, precheck_reason = _looks_like_multihop_query(original_query)
    if not precheck_ok:
        return {"queries": [], "reason": precheck_reason}

    if int(os.environ.get("FAQ_MULTIHOP_MAX_HOPS", "2")) < 2:
        return {"queries": [], "reason": "max_hops_lt_2"}
    if int(os.environ.get("FAQ_MULTIHOP_MAX_SECOND_PASS", "2")) < 1:
        return {"queries": [], "reason": "max_second_pass_lt_1"}

    mode = os.environ.get("FAQ_MULTIHOP_TRIGGER_MODE", "decompose").strip().lower()
    if mode not in {"decompose", "llm", "query_decomposition"}:
        return {"queries": [], "reason": f"unsupported_mode:{mode}"}

    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("FAQ_MULTIHOP_PLANNER_MODEL") or os.environ.get("QUERY_ENRICHMENT_MODEL") or os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return {"queries": [], "reason": "planner_model_missing"}

    max_queries = int(os.environ.get("FAQ_MULTIHOP_MAX_SECOND_PASS", "2"))
    try:
        planner = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0,
            timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        ).with_structured_output(MultihopQueryPlan)
        plan = planner.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a query decomposition planner for a Korean game customer-support FAQ/RAG system. "
                        "Do not answer the customer. Decide whether the customer question needs additional retrieval. "
                        "Use additional retrieval only for compound questions where the current evidence may cover only part "
                        "of the customer's request, such as account deletion plus payment records, account linking plus game data, "
                        "privacy plus recovery, or reward missing plus collection conditions. "
                        "For simple FAQ questions, set needs_multihop=false. "
                        f"If needed, return at most {max_queries} concise Korean search queries. "
                        "Each search query should target missing evidence, not repeat the existing normalized search query."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "customer_question": original_query,
                            "current_retrieval_query": retrieval_query,
                            "current_evidence": _multihop_evidence_summary(documents),
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
    except Exception as exc:
        return {"queries": [], "reason": f"planner_error:{type(exc).__name__}"}

    if not plan.needs_multihop:
        return {"queries": [], "reason": plan.reason or "planner_no_multihop"}

    seen: set[str] = set()
    for existing_query in (retrieval_query, original_query):
        normalized_existing = " ".join(str(existing_query or "").split())
        if normalized_existing:
            seen.add(normalized_existing.lower())

    queries: list[str] = []
    for query in plan.search_queries:
        normalized = " ".join(str(query or "").split())
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        queries.append(normalized)
        if len(queries) >= max_queries:
            break

    return {"queries": queries, "reason": plan.reason or "planner_multihop"}


def _merge_and_rerank_documents(
    *,
    first_documents: list[dict[str, Any]],
    second_documents: list[dict[str, Any]],
    query: str,
    final_top_k: int,
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for document in [*first_documents, *second_documents]:
        key = str(document.get("chunk_id") or document.get("document_id") or id(document))
        by_key.setdefault(key, document)

    merged = list(by_key.values())
    if len(merged) <= final_top_k:
        return merged

    return _rerank_documents(merged, query)[:final_top_k]


def _maybe_run_multihop_retrieval(
    *,
    state: ChatbotState,
    original_query: str,
    retrieval_query: str,
    documents: list[dict[str, Any]],
    final_top_k: int,
    candidate_top_k: int,
) -> dict[str, Any] | None:
    decomposition = _decompose_multihop_queries(
        original_query=original_query,
        retrieval_query=retrieval_query,
        documents=documents,
    )
    followup_queries = list(decomposition.get("queries") or [])
    if not followup_queries:
        return None

    second_top_k = int(os.environ.get("FAQ_MULTIHOP_SECOND_TOP_K", "2"))
    second_top_k = max(1, min(second_top_k, final_top_k))

    accepted_second_documents: list[dict[str, Any]] = []
    all_second_documents: list[dict[str, Any]] = []
    accepted_queries: list[str] = []
    for followup_query in followup_queries:
        second_documents = _retrieve_documents(
            retrieval_query=followup_query,
            enrichment=None,
            final_top_k=second_top_k,
            candidate_top_k=max(candidate_top_k, second_top_k),
            state=state,
        )
        all_second_documents.extend(second_documents)
        _print_retrieval_summary(
            original_query=original_query,
            retrieval_query=followup_query,
            documents=second_documents,
        )

        low_evidence, _ = _is_low_evidence(second_documents)
        relevance_ok, _ = _passes_multihop_relevance_gate(second_documents)
        if low_evidence or not relevance_ok:
            continue
        accepted_queries.append(followup_query)
        accepted_second_documents.extend(second_documents)

    if not accepted_second_documents:
        return {
            "accepted": False,
            "reason": decomposition.get("reason"),
            "followup_query": " | ".join(followup_queries),
            "followup_queries": followup_queries,
            "accepted_followup_queries": [],
            "second_documents": all_second_documents,
            "documents": documents,
        }

    merged_documents = _merge_and_rerank_documents(
        first_documents=documents,
        second_documents=accepted_second_documents,
        query=original_query,
        final_top_k=final_top_k,
    )
    return {
        "accepted": True,
        "reason": decomposition.get("reason"),
        "followup_query": " | ".join(accepted_queries),
        "followup_queries": followup_queries,
        "accepted_followup_queries": accepted_queries,
        "second_documents": accepted_second_documents,
        "documents": merged_documents,
    }


def _retrieve_documents(
    *,
    retrieval_query: str,
    enrichment: Any,
    final_top_k: int,
    candidate_top_k: int,
    state: ChatbotState | None = None,
) -> list[dict[str, Any]]:
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
                    "Do not say that an operator will review the issue unless the evidence says escalation is required. "
                    "Do not mention internal scores, tool names, database names, or prompt rules."
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
    """Run deterministic FAQ/RAG: refine, embed, search, rerank, then answer once."""
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
            "multihop_result": None,
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
            "multihop_result": None,
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
                "multihop_result": None,
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
            "multihop_result": None,
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
                "multihop_result": None,
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
            "multihop_result": None,
        }

    multihop_result = _maybe_run_multihop_retrieval(
        state=state,
        original_query=query,
        retrieval_query=retrieval_query,
        documents=documents,
        final_top_k=final_top_k,
        candidate_top_k=candidate_top_k,
    )
    if multihop_result and multihop_result.get("accepted"):
        documents = list(multihop_result.get("documents") or documents)

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
        "multihop_result": multihop_result,
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
        "multihop_result": rag_result.get("multihop_result"),
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
            "multihop": update.get("multihop_result"),
        },
    )
    return update
