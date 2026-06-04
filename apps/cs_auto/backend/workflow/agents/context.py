"""Context loading and retrieval helpers for the active operation workflow."""

from __future__ import annotations

import re
from typing import Any

from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from common.db.connection import db_connection
from common.llm.client import get_query_embedding

from ..state import EvidenceDocument, OperationState, QueryRoute, TargetRoute


class ContextAgentResult(BaseModel):
    """Merged context and retrieval payload for downstream nodes."""

    context: dict[str, Any] = Field(default_factory=dict)
    context_nodes: list[str] = Field(default_factory=list)
    retrieved_docs: list[EvidenceDocument] = Field(default_factory=list)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# _query_text ?? ??
def _query_text(state: OperationState) -> str:
    query_text = state.query_text or state.ticket.body or state.ticket.title
    if not query_text:
        raise ValueError("operation workflow requires query_text or ticket body")
    return query_text


# _keyword_terms ?? ??
def _keyword_terms(query_text: str) -> list[str]:
    terms = re.findall(r"[0-9A-Za-z가-힣]{2,}", query_text)
    stopwords = {"윈도우", "확인", "싶습니다", "포함", "되는지", "나온"}
    seen: set[str] = set()
    keywords: list[str] = []
    for term in terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        keywords.append(term)
    return keywords[:6]


# _rrf_merge ?? ??
def _rrf_merge(
    keyword_rows: dict[str, dict[str, Any]],
    vector_rows: dict[str, dict[str, Any]],
    *,
    top_k: int = 8,
    k: int = 60,
) -> list[dict[str, Any]]:
    keyword_ranks = {
        cid: rank
        for rank, cid in enumerate(
            sorted(keyword_rows, key=lambda x: -(keyword_rows[x].get("score") or 0.0)),
            start=1,
        )
    }
    vector_ranks = {
        cid: rank
        for rank, cid in enumerate(
            sorted(vector_rows, key=lambda x: -(vector_rows[x].get("score") or 0.0)),
            start=1,
        )
    }

    scored: list[tuple[float, dict[str, Any]]] = []
    for cid in set(keyword_rows) | set(vector_rows):
        score = 0.0
        if cid in keyword_ranks:
            score += 1.0 / (k + keyword_ranks[cid])
        if cid in vector_ranks:
            score += 1.0 / (k + vector_ranks[cid])
        scored.append((score, keyword_rows.get(cid) or vector_rows[cid]))
    scored.sort(key=lambda item: -item[0])
    return [row for _, row in scored[:top_k]]


# _retrieve_docs ?? ??
def _retrieve_docs(state: OperationState) -> list[EvidenceDocument]:
    query_text = _query_text(state)
    query_embedding = get_query_embedding(query_text)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
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
            keyword_rows = {row["chunk_id"]: dict(row) for row in cur.fetchall()}

            if not keyword_rows:
                terms = _keyword_terms(query_text)
                if terms:
                    conditions = " OR ".join(["c.chunk_text ILIKE %s OR d.title ILIKE %s"] * len(terms))
                    params = [f"%{term}%" for term in terms for _ in range(2)]
                    cur.execute(
                        f"""
                        SELECT
                            c.chunk_id,
                            c.document_id,
                            d.source_type,
                            d.category,
                            d.title,
                            c.chunk_text,
                            0.1 AS score
                        FROM documents_chunks c
                        JOIN documents d ON d.documents_id = c.document_id
                        WHERE {conditions}
                        ORDER BY c.created_at DESC NULLS LAST
                        LIMIT 10
                        """,
                        tuple(params),
                    )
                    keyword_rows = {row["chunk_id"]: dict(row) for row in cur.fetchall()}

            vector_rows: dict[str, dict[str, Any]] = {}
            if query_embedding:
                embedding_literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
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

    merged = _rrf_merge(keyword_rows, vector_rows, top_k=3)
    return [
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


# run_context_agent ?? ??
def run_context_agent(
    *,
    state: OperationState,
    route: QueryRoute,
    target_route: TargetRoute,
    context_rows: list[dict[str, Any]],
    context_node_name: str,
) -> ContextAgentResult:
    """Merge route-specific context and perform retrieval for reply paths."""

    context = {**state.context, route: context_rows}
    context_nodes = [*state.context_nodes, context_node_name]
    retrieved_docs: list[EvidenceDocument] = []
    evidence_doc_ids: list[str] = []
    errors = list(state.errors)

    if target_route == "rag_reply":
        prepared_state = state.model_copy(update={"context": context, "context_nodes": context_nodes})
        retrieved_docs = _retrieve_docs(prepared_state)
        evidence_doc_ids = [doc.doc_id for doc in retrieved_docs if doc.doc_id]

    return ContextAgentResult(
        context=context,
        context_nodes=context_nodes,
        retrieved_docs=retrieved_docs,
        evidence_doc_ids=evidence_doc_ids,
        errors=errors,
    )
