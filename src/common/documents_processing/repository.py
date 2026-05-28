"""Database persistence helpers for the documents processing pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg.rows import dict_row

from src.common.db.connection import db_connection

from .types import ChunkRecord, DocumentRecord, EmbeddingRecord


class DocumentsProcessingRepository:
    """Repository for loading source documents and storing derived search data."""

    def load_documents(
        self,
        *,
        document_id: str | None = None,
        source_type: str | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[DocumentRecord]:
        clauses = ["COALESCE(BTRIM(raw_content), '') <> ''"]
        params: list[Any] = []
        if document_id:
            clauses.append("documents_id = %s")
            params.append(document_id)
        if source_type:
            clauses.append("source_type = %s")
            params.append(source_type)
        if category:
            clauses.append("category = %s")
            params.append(category)

        query = f"""
            SELECT documents_id, source_type, category, title, raw_content, source_url, published_at, updated_at
            FROM documents
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC NULLS LAST, published_at DESC NULLS LAST, documents_id ASC
        """
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        return [
            DocumentRecord(
                document_id=row["documents_id"],
                source_type=row.get("source_type"),
                category=row.get("category"),
                title=row.get("title"),
                raw_content=row.get("raw_content"),
                source_url=row.get("source_url"),
                published_at=row.get("published_at"),
                updated_at=row.get("updated_at"),
            )
            for row in rows
        ]

    def rebuild_document_artifacts(
        self,
        *,
        document_id: str,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[EmbeddingRecord],
    ) -> None:
        with db_connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM documents_chunks WHERE document_id = %s", (document_id,))
                    if chunks:
                        cur.executemany(
                            """
                            INSERT INTO documents_chunks (chunk_id, document_id, chunk_text, chunk_order, token_count)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            [
                                (
                                    chunk.chunk_id,
                                    chunk.document_id,
                                    chunk.chunk_text,
                                    chunk.chunk_order,
                                    chunk.token_count,
                                )
                                for chunk in chunks
                            ],
                        )
                    if embeddings:
                        cur.executemany(
                            """
                            INSERT INTO documents_embeddings (
                                embedding_id, chunk_id, embedding_vector, embedding_model, source_type, category
                            )
                            VALUES (%s, %s, %s::vector, %s, %s, %s)
                            """,
                            [
                                (
                                    embedding.embedding_id,
                                    embedding.chunk_id,
                                    _vector_literal(embedding.embedding_vector),
                                    embedding.embedding_model,
                                    embedding.source_type,
                                    embedding.category,
                                )
                                for embedding in embeddings
                            ],
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
