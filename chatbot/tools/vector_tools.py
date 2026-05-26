from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

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
def search_documents(embedding_json: str, top_k: int | None = None) -> str:
    """Search document chunks by cosine similarity to the given embedding.

    Args:
        embedding_json: JSON-encoded float list produced by embed_query.
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

    scored = []
    for chunk in chunks:
        cid = chunk["chunk_id"]
        if cid in vec_by_chunk:
            score = _cosine(query_vec, vec_by_chunk[cid])
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [{"score": round(s, 4), **c} for s, c in scored[:k]]
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
