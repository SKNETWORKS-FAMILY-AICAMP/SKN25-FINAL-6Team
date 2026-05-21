from __future__ import annotations

import json
import math
import os
import re
import sys
from html import unescape
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from psycopg.rows import dict_row

from chatbot.observability.logger import log_event
from config import settings
from src.common.db.connection import db_connection

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"


def _embedding_model_name() -> str:
    raw = settings.embedding_model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return raw.split(":", 1)[1] if raw.startswith("openai:") else raw


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def _clean_text(text: str, max_chars: int) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", unescape(text or ""))
    collapsed = re.sub(r"\s+", " ", without_tags).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _compact_results(results: list[dict]) -> list[dict]:
    max_chars = _clamp(_env_int("FAQ_RAG_CHUNK_CHARS", 700), 120, 1500)
    compact = []
    for rank, row in enumerate(results, start=1):
        compact.append({
            "rank": rank,
            "score": row.get("score"),
            "chunk_id": row.get("chunk_id"),
            "document_id": row.get("document_id"),
            "source_type": row.get("source_type"),
            "title": _clean_text(row.get("title", ""), 120),
            "chunk_text": _clean_text(row.get("chunk_text", ""), max_chars),
        })
    return compact


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _parse_vector(raw_vector: object) -> list[float]:
    raw = str(raw_vector or "").strip().strip("[]")
    return [float(value) for value in raw.split(",") if value.strip()]


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
        api_key=settings.openai_api_key,
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
    """Search DB document chunks using keyword and cosine similarity.

    Args:
        embedding_json: JSON-encoded float list produced by embed_query.
        query_text: Original query text for keyword search.
        top_k: Number of top results to return. Defaults to RETRIEVAL_TOP_K.
    """
    requested_k = top_k or settings.retrieval_top_k or _env_int("RETRIEVAL_TOP_K", 3)
    max_k = _clamp(_env_int("FAQ_RAG_MAX_RESULTS", 2), 1, 5)
    k = _clamp(requested_k, 1, max_k)
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
        db_vector = _parse_vector(row.pop("embedding_vector", ""))
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
    return json.dumps(_compact_results(results), ensure_ascii=False)


@tool(parse_docstring=True)
def rerank_documents(docs_json: str, query: str) -> str:
    """Rerank retrieved document chunks by relevance to the query.

    Args:
        docs_json: JSON-encoded list of document chunks from search_documents.
        query: Original user query for relevance comparison.
    """
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="rerank_documents",
        metadata={"query_length": len(query), "docs_json_length": len(docs_json)},
    )
    return docs_json
