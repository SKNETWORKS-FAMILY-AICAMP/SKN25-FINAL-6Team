"""Shared retrieval layer for embedding, vector search, and reranking workflows."""

from common.retrieval.cache_store import (
    clear_faq_cache,
    get_cached_retrieval,
    get_cached_session_state,
    set_cached_retrieval,
    set_cached_session_state,
)
from common.retrieval.embeddings import embed_query
from common.retrieval.retriever import rerank_documents, search_document_chunks, search_documents
from common.retrieval.vector_tools import (
    RetrievalQuery,
    enrich_retrieval_query,
    hybrid_rank_documents,
    refine_query_text,
    refine_retrieval_query,
)


__all__ = [
    "RetrievalQuery",
    "clear_faq_cache",
    "embed_query",
    "enrich_retrieval_query",
    "get_cached_retrieval",
    "get_cached_session_state",
    "hybrid_rank_documents",
    "refine_query_text",
    "refine_retrieval_query",
    "rerank_documents",
    "search_document_chunks",
    "search_documents",
    "set_cached_retrieval",
    "set_cached_session_state",
]
