from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from psycopg.rows import dict_row
from src.common.db.connection import db_connection
from chatbot.observability.logger import EVENT_TOOL_COMPLETED, EVENT_TOOL_STARTED, log_event

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


def _embedding_model_name() -> str:
    raw = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return raw.split(":", 1)[1] if raw.startswith("openai:") else raw


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _rrf_fuse(
    cosine_ranked: list[tuple[float, dict]],
    bm25_ranked: list[tuple[float, dict]],
    k: int = 60,
) -> list[tuple[float, dict]]:
    chunk_by_id = {c["chunk_id"]: c for _, c in cosine_ranked}
    cosine_rank = {c["chunk_id"]: i for i, (_, c) in enumerate(cosine_ranked)}
    bm25_rank = {c["chunk_id"]: i for i, (_, c) in enumerate(bm25_ranked)}
    fused = []
    for cid in set(cosine_rank) | set(bm25_rank):
        rrf = (
            1 / (k + cosine_rank.get(cid, len(cosine_rank)) + 1)
            + 1 / (k + bm25_rank.get(cid, len(bm25_rank)) + 1)
        )
        fused.append((rrf, chunk_by_id[cid]))
    fused.sort(key=lambda x: x[0], reverse=True)
    return fused


@tool(parse_docstring=True)
def embed_query(text: str) -> str:
    """Generate an embedding vector for the given query text.

    Args:
        text: Query text to embed.
    """
    log_event(
        EVENT_TOOL_STARTED,
        tool_name="embed_query",
        metadata={"text_length": len(text)},
    )
    client = OpenAIEmbeddings(
        model=_embedding_model_name(),
        api_key=os.environ.get("LLM_API_KEY"),
    )
    vector = client.embed_query(text)
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="embed_query",
        metadata={"vector_size": len(vector)},
    )
    return json.dumps(vector)


@tool(parse_docstring=True)
def search_documents(embedding_json: str, query_text: str = "", top_k: int | None = None) -> str:
    """Search document chunks using hybrid BM25 + cosine similarity (RRF fusion).

    Args:
        embedding_json: JSON-encoded float list produced by embed_query.
        query_text: Original query text for BM25 keyword search. If empty, uses cosine only.
        top_k: Number of top results to return. Defaults to RETRIEVAL_TOP_K.
    """
    k = top_k or int(os.environ.get("RETRIEVAL_TOP_K", "3"))
    query_vec: list[float] = json.loads(embedding_json)
    log_event(
        EVENT_TOOL_STARTED,
        tool_name="search_documents",
        metadata={"query_text": query_text, "top_k": k},
    )

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
                    e.embedding_vector::text AS embedding_vector,
                    ts_rank_cd(
                        to_tsvector('simple', c.chunk_text),
                        plainto_tsquery('simple', %s)
                    ) AS keyword_score
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                JOIN documents_embeddings e ON e.chunk_id = c.chunk_id
                WHERE
                    %s = ''
                    OR to_tsvector('simple', c.chunk_text) @@ plainto_tsquery('simple', %s)
                    OR c.chunk_text ILIKE %s
                    OR d.title ILIKE %s
                ORDER BY keyword_score DESC NULLS LAST, c.created_at DESC NULLS LAST
                LIMIT 50
                """,
                (query_text, query_text, query_text, f"%{query_text}%", f"%{query_text}%"),
            )
            rows = [dict(row) for row in cur.fetchall()]

    scored = []
    for row in rows:
        raw_vector = str(row.pop("embedding_vector", "")).strip("[]")
        db_vector = [float(value) for value in raw_vector.split(",") if value.strip()]
        cosine_score = _cosine(query_vec, db_vector) if db_vector else 0.0
        keyword_score = float(row.pop("keyword_score") or 0.0)
        scored.append((cosine_score + keyword_score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [{"score": round(score, 4), **row} for score, row in scored[:k]]
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="search_documents",
        metadata={"candidate_count": len(rows), "result_count": len(results)},
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool(parse_docstring=True)
def rerank_documents(docs_json: str, query: str) -> str:
    """Rerank retrieved document chunks by relevance to the query.

    Args:
        docs_json: JSON-encoded list of document chunks from search_documents.
        query: Original user query for relevance comparison.
    """
    # Baseline: pass-through. Swap in a cross-encoder or LLM reranker when ready.
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="rerank_documents",
        metadata={"query_length": len(query), "docs_json_length": len(docs_json)},
    )
    return docs_json
