from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from rank_bm25 import BM25Okapi

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from config import settings
from data.seed_payload import SEED_DOCUMENT_CHUNKS, SEED_DOCUMENT_EMBEDDINGS, clone_payload


def _embedding_model_name() -> str:
    raw = settings.embedding_model
    return raw.split(":", 1)[1] if raw.startswith("openai:") else raw


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _bm25_scores(chunks: list[dict], query_text: str) -> dict[str, float]:
    texts = [c["chunk_text"] for c in chunks]
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query_text.lower().split())
    return {c["chunk_id"]: float(s) for c, s in zip(chunks, scores)}


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
    client = OpenAIEmbeddings(
        model=_embedding_model_name(),
        api_key=settings.openai_api_key,
    )
    vector = client.embed_query(text)
    return json.dumps(vector)


@tool(parse_docstring=True)
def search_documents(embedding_json: str, query_text: str = "", top_k: int | None = None) -> str:
    """Search document chunks using hybrid BM25 + cosine similarity (RRF fusion).

    Args:
        embedding_json: JSON-encoded float list produced by embed_query.
        query_text: Original query text for BM25 keyword search. If empty, uses cosine only.
        top_k: Number of top results to return. Defaults to RETRIEVAL_TOP_K.
    """
    k = top_k or settings.retrieval_top_k
    query_vec: list[float] = json.loads(embedding_json)

    chunks = clone_payload(SEED_DOCUMENT_CHUNKS)
    embeddings = clone_payload(SEED_DOCUMENT_EMBEDDINGS)

    vec_by_chunk: dict[str, list[float]] = {
        row["chunk_id"]: row["embedding_vector"]
        for row in embeddings
        if row.get("embedding_vector")
    }

    cosine_scored = []
    for chunk in chunks:
        cid = chunk["chunk_id"]
        if cid in vec_by_chunk:
            score = _cosine(query_vec, vec_by_chunk[cid])
            cosine_scored.append((score, chunk))
    cosine_scored.sort(key=lambda x: x[0], reverse=True)

    if query_text:
        bm25_raw = _bm25_scores(chunks, query_text)
        bm25_scored = sorted(
            [(bm25_raw.get(c["chunk_id"], 0.0), c) for c in chunks],
            key=lambda x: x[0],
            reverse=True,
        )
        final = _rrf_fuse(cosine_scored, bm25_scored)
    else:
        final = cosine_scored

    results = [{"score": round(s, 4), **c} for s, c in final[:k]]
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool(parse_docstring=True)
def rerank_documents(docs_json: str, query: str) -> str:
    """Rerank retrieved document chunks by relevance to the query.

    Args:
        docs_json: JSON-encoded list of document chunks from search_documents.
        query: Original user query for relevance comparison.
    """
    # Baseline: pass-through. Swap in a cross-encoder or LLM reranker when ready.
    return docs_json
