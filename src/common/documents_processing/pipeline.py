"""End-to-end orchestration for document chunk and embedding generation."""

from __future__ import annotations

import logging
from typing import Protocol

from .chunking import chunk_document
from .embed import OpenAIChunkEmbedder
from .normalize import normalize_document_text
from .repository import DocumentsProcessingRepository
from .types import BatchProcessingResult, DocumentProcessingResult, DocumentRecord


LOGGER = logging.getLogger(__name__)


class ChunkEmbedder(Protocol):
    model_name: str

    def embed_chunks(self, chunks): ...


def rebuild_document_chunks_and_embeddings(
    document: DocumentRecord,
    *,
    repository: DocumentsProcessingRepository | None = None,
    embedder: ChunkEmbedder | None = None,
    dry_run: bool = False,
) -> DocumentProcessingResult:
    """Normalize, chunk, embed, and persist one source document."""

    repository = repository or DocumentsProcessingRepository()
    raw_text = document.raw_content or ""
    normalized_text = normalize_document_text(raw_text)
    if not normalized_text:
        return DocumentProcessingResult(
            document_id=document.document_id,
            success=True,
            skipped=True,
            skip_reason="normalized document text is empty",
        )

    chunks = chunk_document(document, normalized_text)
    if not chunks:
        return DocumentProcessingResult(
            document_id=document.document_id,
            success=True,
            skipped=True,
            skip_reason="no valid chunks generated",
        )

    if dry_run:
        return DocumentProcessingResult(
            document_id=document.document_id,
            success=True,
            chunk_count=len(chunks),
            embedding_count=len(chunks),
        )

    active_embedder = embedder or OpenAIChunkEmbedder()
    embeddings = active_embedder.embed_chunks(chunks)
    repository.rebuild_document_artifacts(
        document_id=document.document_id,
        chunks=chunks,
        embeddings=embeddings,
    )
    return DocumentProcessingResult(
        document_id=document.document_id,
        success=True,
        chunk_count=len(chunks),
        embedding_count=len(embeddings),
    )


def run_documents_pipeline(
    *,
    repository: DocumentsProcessingRepository | None = None,
    embedder: ChunkEmbedder | None = None,
    document_id: str | None = None,
    source_type: str | None = None,
    category: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> BatchProcessingResult:
    """Process source documents into searchable chunks and embeddings."""

    repository = repository or DocumentsProcessingRepository()
    documents = repository.load_documents(
        document_id=document_id,
        source_type=source_type,
        category=category,
        limit=limit,
    )

    result = BatchProcessingResult(total_documents=len(documents))
    active_embedder = None if dry_run else (embedder or OpenAIChunkEmbedder())

    for document in documents:
        try:
            doc_result = rebuild_document_chunks_and_embeddings(
                document,
                repository=repository,
                embedder=active_embedder,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("documents processing failed for %s", document.document_id)
            doc_result = DocumentProcessingResult(
                document_id=document.document_id,
                success=False,
                error=str(exc),
            )

        result.results.append(doc_result)
        if doc_result.success and not doc_result.skipped:
            result.processed_documents += 1
            result.total_chunks += doc_result.chunk_count
            result.total_embeddings += doc_result.embedding_count
        elif doc_result.skipped:
            result.skipped_documents += 1
        else:
            result.failed_documents += 1

    return result
