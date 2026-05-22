from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from chatbot.retrieval.vector_tools import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks


@dataclass(frozen=True)
class FaqRagContext:
    raw_query: str
    retrieval_query: str
    retrieval_enrichment: dict[str, Any]
    documents: list[dict[str, Any]]
    retrieval_trace: list[dict[str, Any]]


def retrieve_faq_context(raw_query: str, *, top_k: int = 5) -> FaqRagContext:
    """Run the same function-based retrieval path used by the FAQ agent."""
    enrichment = enrich_retrieval_query(raw_query)
    retrieval_query = enrichment.query_text
    embedding_json = embed_query.invoke({"text": retrieval_query})
    documents = search_document_chunks(
        embedding_json=embedding_json,
        query_text=retrieval_query,
        top_k=top_k,
        prefer_faq=True,
        enrichment=enrichment,
    )
    reranked_json = rerank_documents.invoke(
        {
            "docs_json": json.dumps(documents, ensure_ascii=False),
            "query": retrieval_query,
        }
    )
    documents = json.loads(reranked_json)
    return FaqRagContext(
        raw_query=raw_query,
        retrieval_query=retrieval_query,
        retrieval_enrichment=enrichment.model_dump(),
        documents=documents,
        retrieval_trace=[
            {"step": "enrich_retrieval_query", "input": raw_query, "output": enrichment.model_dump()},
            {"step": "embed_query", "input": retrieval_query},
            {"step": "search_document_chunks", "top_k": top_k, "prefer_faq": True},
            {"step": "rerank_documents", "input_count": len(documents)},
        ],
    )


def format_contexts(documents: list[dict[str, Any]]) -> list[str]:
    """Return RAGAS-friendly context strings from retrieved document chunks."""
    contexts = []
    for doc in documents:
        title = doc.get("title") or "untitled"
        chunk_text = doc.get("chunk_text") or ""
        contexts.append(f"[{title}]\n{chunk_text}")
    return contexts
