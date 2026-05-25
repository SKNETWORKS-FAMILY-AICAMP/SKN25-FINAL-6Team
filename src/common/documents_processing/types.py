"""Types shared by the documents processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, frozen=True)
class DocumentRecord:
    document_id: str
    source_type: str | None
    category: str | None
    title: str | None
    raw_content: str | None
    source_url: str | None
    published_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True, frozen=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_text: str
    chunk_order: int
    token_count: int
    source_type: str | None = None
    category: str | None = None


@dataclass(slots=True, frozen=True)
class EmbeddingRecord:
    embedding_id: str
    chunk_id: str
    embedding_vector: list[float]
    embedding_model: str
    source_type: str | None
    category: str | None


@dataclass(slots=True)
class DocumentProcessingResult:
    document_id: str
    success: bool
    chunk_count: int = 0
    embedding_count: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class BatchProcessingResult:
    total_documents: int = 0
    processed_documents: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    results: list[DocumentProcessingResult] = field(default_factory=list)

