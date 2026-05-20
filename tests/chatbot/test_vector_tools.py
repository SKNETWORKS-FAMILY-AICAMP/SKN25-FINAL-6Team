from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")

from chatbot.retrieval.vector_tools import rerank_documents, search_documents
from data.seed_payload import SEED_DOCUMENT_EMBEDDINGS


def _invoke(tool, payload: dict) -> str:
    return tool.invoke(payload)


def test_search_documents_returns_matching_seed_chunk_for_same_embedding() -> None:
    seed_embedding = SEED_DOCUMENT_EMBEDDINGS[0]
    embedding_json = json.dumps(seed_embedding["embedding_vector"])

    raw = _invoke(search_documents, {"embedding_json": embedding_json, "top_k": 3})
    results = json.loads(raw)

    assert results
    assert results[0]["chunk_id"] == seed_embedding["chunk_id"]
    assert results[0]["score"] > 0.99


def test_search_documents_respects_top_k() -> None:
    seed_embedding = SEED_DOCUMENT_EMBEDDINGS[0]
    embedding_json = json.dumps(seed_embedding["embedding_vector"])

    raw = _invoke(search_documents, {"embedding_json": embedding_json, "top_k": 2})
    results = json.loads(raw)

    assert len(results) <= 2


def test_rerank_documents_is_pass_through_for_baseline() -> None:
    docs_json = json.dumps([
        {"chunk_id": "FAQ-101-1", "score": 1.0},
        {"chunk_id": "FAQ-102-1", "score": 0.8},
    ])

    result = _invoke(rerank_documents, {"docs_json": docs_json, "query": "결제 보상"})

    assert result == docs_json
