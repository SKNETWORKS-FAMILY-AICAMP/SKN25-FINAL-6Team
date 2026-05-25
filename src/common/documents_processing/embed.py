"""Embedding generation for document chunks."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from .types import ChunkRecord, EmbeddingRecord


load_dotenv()


class OpenAIChunkEmbedder:
    """Embed chunk texts using the configured OpenAI embedding model."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("LLM_API_KEY is required to generate document embeddings")
        self._embedder = OpenAIEmbeddings(model=self.model_name, api_key=api_key)

    def embed_chunks(self, chunks: list[ChunkRecord]) -> list[EmbeddingRecord]:
        if not chunks:
            return []
        vectors = self._embedder.embed_documents([chunk.chunk_text for chunk in chunks])
        return [
            EmbeddingRecord(
                embedding_id=f"{chunk.chunk_id}::embedding",
                chunk_id=chunk.chunk_id,
                embedding_vector=list(vector),
                embedding_model=self.model_name,
                source_type=chunk.source_type,
                category=chunk.category,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
