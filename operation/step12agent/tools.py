from __future__ import annotations

import json
import math
from typing import Any

from langchain_core.tools import tool
from rank_bm25 import BM25Okapi

from config import settings

try:
    from kiwipiepy import Kiwi as _Kiwi
    _kiwi = _Kiwi()
except Exception:
    _kiwi = None


# ── BM25 유틸 ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """한국어 형태소 분석(kiwipiepy) 기반 토크나이저. 설치 안 된 경우 공백 분리로 폴백한다."""
    if _kiwi is not None:
        return [token.form for token in _kiwi.tokenize(text)]
    return text.split()


def _bm25_retrieve(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int,
) -> list[tuple[dict[str, Any], float]]:
    """BM25로 chunks에서 query와 가장 관련 있는 상위 top_k 청크를 반환한다."""
    corpus = [_tokenize(c["chunk_text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(chunks, scores.tolist()), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ── Vector 유틸 ───────────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 반환한다. 영벡터면 0.0을 반환한다."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(x ** 2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_query_embedding(query: str) -> list[float] | None:
    """settings.embedding_model로 query embedding을 생성한다.

    API 호출 실패 시 None을 반환하며, 호출부에서 BM25 단독 모드로 폴백한다.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        embedder = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )
        return embedder.embed_query(query)
    except Exception:
        # 임베딩 실패 시 BM25 단독 검색으로 폴백한다
        return None


def _chroma_score_map(query: str, n_results: int) -> dict[str, float]:
    """Chroma PersistentClient로 vector 검색 후 chunk_id → similarity 점수를 반환한다.

    Chroma cosine distance: distance = 1 - cosine_similarity → similarity = 1 - distance.
    컬렉션이 없거나 임베딩 실패 시 빈 dict를 반환하며 호출부에서 BM25 단독으로 폴백한다.
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_collection(settings.vector_collection)
        total = collection.count()
        if total == 0:
            return {}
        query_vector = _get_query_embedding(query)
        if query_vector is None:
            return {}
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(n_results, total),
            include=["distances"],
        )
        ids = results["ids"][0]
        distances = results["distances"][0]
        return {cid: 1.0 - dist for cid, dist in zip(ids, distances)}
    except Exception:
        # 컬렉션 미존재 / CHROMA_PERSIST_DIR 경로 오류 / 임베딩 API 실패 모두 빈 dict로 폴백한다
        return {}


def _vector_retrieve(
    query_vector: list[float],
    chunks: list[dict[str, Any]],
    embeddings: list[dict[str, Any]],
) -> dict[str, float]:
    """chunk_id별 vector similarity 점수를 반환한다.

    documents_embeddings의 chunk_id를 기준으로 query_vector와 코사인 유사도를 계산한다.
    """
    # chunk_id → embedding_vector 조회용 dict
    chunk_vec_map: dict[str, list[float]] = {
        emb["chunk_id"]: emb["embedding_vector"]
        for emb in embeddings
    }

    scores: dict[str, float] = {}
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")
        vec = chunk_vec_map.get(chunk_id)
        if vec is None:
            # documents_embeddings에 해당 chunk_id 항목이 없으면 점수 계산 불가 — 건너뛴다
            continue
        scores[chunk_id] = _cosine_similarity(query_vector, vec)
    return scores


# ── Hybrid Retrieval ──────────────────────────────────────────────────────────

def _hybrid_retrieve(
    query: str,
    chunks: list[dict[str, Any]],
    embeddings: list[dict[str, Any]],
    top_k: int,
) -> list[tuple[dict[str, Any], float]]:
    """BM25와 vector 검색의 순위를 RRF로 결합해 상위 top_k chunk를 반환한다.

    RRF score = 1/(k + bm25_rank) + 1/(k + vector_rank)  (k = settings.rrf_k, 기본 60)
    vector 검색 불가 시 BM25 순위만으로 단독 동작한다.
    """
    k = settings.rrf_k
    default_rank = len(chunks) + 1  # 결과에 없는 chunk에 부여하는 패널티 순위

    # BM25: 전체 chunks 순위 맵
    bm25_ranked = _bm25_retrieve(query, chunks, len(chunks))
    bm25_rank_map = {c["chunk_id"]: rank for rank, (c, _) in enumerate(bm25_ranked, 1)}

    # Vector: Chroma 설정 여부에 따라 점수 맵을 결정한다
    if settings.chroma_persist_dir:
        vec_scores = _chroma_score_map(query, len(chunks))
    else:
        query_vector = _get_query_embedding(query)
        vec_scores = _vector_retrieve(query_vector, chunks, embeddings) if query_vector else {}

    # 점수 내림차순 정렬로 vector 순위 맵을 생성한다
    vec_rank_map = {
        cid: rank
        for rank, (cid, _) in enumerate(
            sorted(vec_scores.items(), key=lambda x: x[1], reverse=True), 1
        )
    }

    # RRF fusion
    scored = []
    for chunk in chunks:
        cid = chunk["chunk_id"]
        rrf_score = (
            1.0 / (k + bm25_rank_map.get(cid, default_rank)) +
            1.0 / (k + vec_rank_map.get(cid, default_rank))
        )
        scored.append((chunk, rrf_score))

    return sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]


# ── STEP1 도구 ─────────────────────────────────────────────────────────────────

@tool
def record_ticket_analysis(
    category: str,
    risk_level: str,
    sentiment: str,
    routing_target: str,
    summary: str,
) -> str:
    """STEP1 문의 분류 결과를 기록한다.

    LLM이 분류를 완료하면 반드시 이 도구를 호출해야 한다.
    호출 결과(JSON 문자열)는 step1_node에서 ticket_analysis로 추출된다.
    """
    result = {
        "category": category,
        "risk_level": risk_level,
        "sentiment": sentiment,
        "routing_target": routing_target,
        "summary": summary,
    }
    return json.dumps(result, ensure_ascii=False)


# ── STEP2 도구 팩토리 ──────────────────────────────────────────────────────────

def make_retrieve_evidence_tool(knowledge_base: dict[str, Any]):
    """knowledge_base를 클로저로 포획한 retrieve_evidence 도구를 생성해 반환한다.

    LLM에게 knowledge_base 전체를 인자로 넘기지 않고 클로저로 처리하는 이유:
    - knowledge_base JSON이 크면 LLM 토큰 낭비가 심하고 직렬화 오류 위험이 있다.
    - BM25·vector 검색은 Python이 직접 수행하므로 LLM은 query 문자열만 제공하면 된다.
    """

    @tool
    def retrieve_evidence(query: str) -> str:
        """Hybrid(BM25 + vector) 검색으로 근거 문서 청크를 찾고 evidence_docs(JSON)를 반환한다."""
        chunks = knowledge_base.get("documents_chunks", [])
        embeddings = knowledge_base.get("documents_embeddings", [])
        # documents 테이블 PK(documents_id) 값을 키로 dict를 구성한다
        # chunks의 FK 필드명은 document_id이며 값은 동일하므로 아래 조인이 성립한다
        documents: dict[str, dict] = {
            doc["documents_id"]: doc
            for doc in knowledge_base.get("documents", [])
        }

        # BM25 + vector hybrid 검색으로 상위 chunk를 선택한다
        ranked = _hybrid_retrieve(query, chunks, embeddings, settings.retrieval_top_k)

        evidence = []
        for rank, (chunk, score) in enumerate(ranked, start=1):
            doc_id = chunk.get("document_id", "")
            doc = documents.get(doc_id, {})
            evidence.append({
                "source_type": doc.get("source_type", ""),
                "source_id": doc_id,
                "evidence_text": chunk["chunk_text"],
                # RRF score (0~1/k 수준); 0~1 cosine similarity가 아님에 주의
                "relevance_score": round(float(score), 4),
                "retrieval_rank": rank,
            })

        return json.dumps(evidence, ensure_ascii=False)

    return retrieve_evidence
