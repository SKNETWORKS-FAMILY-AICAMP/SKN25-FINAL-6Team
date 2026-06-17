"""Document retrieval layer for CS auto answer generation.

This module handles document retrieval only.
Answer composition across DB and documents must be orchestrated by
the caller, and this module only returns document evidence.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# backend 작업 디렉터리 기준으로 도구 모듈 경로를 맞춘다.
from agents.tool.dbsearch import EvidenceItem
from common.retrieval import embed_query, enrich_retrieval_query, rerank_documents, search_document_chunks


Category = Literal["payment", "refund", "account", "bug", "gacha", "policy", "general"]


# ticket_analysis 전체 대신 문서 검색에 필요한 필드만 정규화하는 입력 모델이다.
# 검색 질의와 fallback 요약을 같은 형식으로 맞춰 후속 클래스에 전달한다.
class RetrievalAnalysis(BaseModel):
    """Subset of ticket_analysis fields needed for document retrieval."""

    model_config = ConfigDict(extra="ignore")

    analysis_id: int | None = None
    category: Category | str = "general"
    enriched_query: str | None = ""
    summary: str | None = ""


# 문서 검색에 사용할 질의 문자열과 개수 옵션을 함께 묶는 모델이다.
# 질의 정제 결과와 검색 옵션을 하나로 유지해 호출부 분기를 줄인다.
class DocumentSearchQuery(BaseModel):
    """Normalized query payload for hybrid documents retrieval."""

    query_text: str
    retrieval_query: str
    prefer_faq: bool = True
    candidate_top_k: int = Field(default=8, ge=1, le=50)
    final_top_k: int = Field(default=5, ge=1, le=20)
    enrichment: dict[str, Any] | None = None


# documents 계열에서 가져온 검색 결과를 중간 표현으로 보관하는 모델이다.
# chunk 메타데이터와 hybrid score를 유지해 evidence 변환 단계에서 재사용한다.
class RetrievedDocument(BaseModel):
    """Normalized hybrid retrieval result from documents tables."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    document_id: str | None = None
    source_type: str | None = None
    category: str | None = None
    title: str | None = None
    chunk_text: str | None = None
    score: float | None = None
    bm25_score: float | None = None
    cosine_score: float | None = None
    candidate_scope: str | None = None
    retrieval_rank: int | None = None


# ticket과 analysis를 바탕으로 문서 검색용 질의를 조립하는 클래스다.
# category는 제한 조건이 아니라 query enrichment에 반영되는 힌트로만 사용한다.
class DocumentQueryBuilder:
    """Build normalized query payloads for documents retrieval."""

    def build(self, ticket: dict[str, object], analysis: dict[str, object]) -> DocumentSearchQuery:
        query_text = str(analysis.get("enriched_query")).strip()
        enrichment = enrich_retrieval_query(query_text)
        candidate_top_k = int(os.environ.get("CS_AUTO_DOC_RETRIEVAL_TOP_K", "8"))
        final_top_k = int(os.environ.get("CS_AUTO_DOC_RETRIEVAL_FINAL_TOP_K", "5"))
        return DocumentSearchQuery(
            query_text=query_text,
            retrieval_query=enrichment.query_text,
            prefer_faq=True,
            candidate_top_k=candidate_top_k,
            final_top_k=final_top_k,
            enrichment=enrichment.model_dump(),
        )


# documents, documents_chunks, documents_embeddings에 대해 hybrid search를 수행하는 클래스다.
# embedding 생성, 후보 검색, rerank를 한 경로로 묶어 문서 검색 책임만 담당한다.
class DocumentsHybridSearcher:
    """Run BM25 + dense hybrid retrieval on documents-family tables."""

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): DocumentsHybridSearcher._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [DocumentsHybridSearcher._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [DocumentsHybridSearcher._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def embed(self, retrieval_query: str) -> str:
        return embed_query.invoke({"text": retrieval_query})

    def search_candidates(self, query: DocumentSearchQuery, embedding_json: str) -> list[dict[str, Any]]:
        return search_document_chunks(
            embedding_json=embedding_json,
            query_text=query.retrieval_query,
            top_k=query.candidate_top_k,
            prefer_faq=query.prefer_faq,
            enrichment=query.enrichment,
        )

    def rerank(self, documents: list[dict[str, Any]], retrieval_query: str) -> list[dict[str, Any]]:
        reranked_json = rerank_documents.invoke(
            {
                "docs_json": json.dumps(self._json_safe(documents), ensure_ascii=False),
                "query": retrieval_query,
            }
        )
        return json.loads(reranked_json)

    def search(self, query: DocumentSearchQuery) -> list[RetrievedDocument]:
        embedding_json = self.embed(query.retrieval_query)
        candidates = self.search_candidates(query, embedding_json)
        reranked = self.rerank(candidates, query.retrieval_query)[: query.final_top_k]
        return [RetrievedDocument.model_validate(document) for document in reranked]


# 문서 검색 결과를 answer_agent 공용 evidence 포맷으로 바꾸는 클래스다.
# source_type, chunk_id, chunk_text를 유지해 초안 생성 근거로 바로 넘길 수 있게 한다.
class DocumentEvidenceAssembler:
    """Convert retrieved documents into answer-agent evidence payloads."""

    def build(self, documents: list[RetrievedDocument]) -> list[dict[str, object]]:
        evidence: list[dict[str, object]] = []
        for rank, document in enumerate(documents, start=1):
            evidence.append(
                EvidenceItem(
                    source_type=str(document.source_type or "documents"),
                    source_id=document.chunk_id,
                    evidence_text=str(document.chunk_text or ""),
                    relevance_score=float(document.score or 0.0),
                    retrieval_rank=int(document.retrieval_rank or rank),
                ).model_dump()
            )
        return evidence


# 문서 검색 관련 클래스를 묶어 answer_agent가 호출할 단일 진입점을 제공하는 클래스다.
# DB 검색과의 조합은 하지 않고, 문서 evidence만 반환하는 역할로 제한한다.
class DocumentRetriever:
    """Top-level document retrieval entrypoint for answer drafting."""

    def __init__(self) -> None:
        self.query_builder = DocumentQueryBuilder()
        self.document_searcher = DocumentsHybridSearcher()
        self.evidence_assembler = DocumentEvidenceAssembler()

    def retrieve(self, ticket: dict[str, object], analysis: dict[str, object]) -> list[dict[str, object]]:
        normalized_analysis = RetrievalAnalysis.model_validate(analysis).model_dump()
        query = self.query_builder.build(ticket, normalized_analysis)
        documents = self.document_searcher.search(query)
        return self.evidence_assembler.build(documents)

    def retrieve_fixed_answer_context(self, analysis: dict[str, object]) -> list[dict[str, object]]:
        normalized_analysis = RetrievalAnalysis.model_validate(analysis)
        return [
            EvidenceItem(
                source_type="fixed_answer",
                source_id=normalized_analysis.analysis_id,
                evidence_text=f"분석 요약: {str(normalized_analysis.summary or '').strip()[:1000]}",
                relevance_score=0.5,
                retrieval_rank=1,
            ).model_dump()
        ]
