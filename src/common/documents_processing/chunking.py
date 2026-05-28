"""Chunking helpers for document search and embedding generation."""

from __future__ import annotations

import re
from typing import Iterable

from .types import ChunkRecord, DocumentRecord


TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+|[^\s]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")


def estimate_token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def _is_heading(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return stripped.startswith("#") or stripped.endswith(":") or stripped.endswith("]")


def _split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in text.split("\n\n")]
    return [part for part in parts if part]


def _split_long_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    if estimate_token_count(paragraph) <= max_tokens:
        return [paragraph.strip()]

    sentences = [piece.strip() for piece in _SENTENCE_SPLIT_RE.split(paragraph) if piece.strip()]
    if len(sentences) <= 1:
        words = TOKEN_RE.findall(paragraph)
        chunks: list[str] = []
        for start in range(0, len(words), max_tokens):
            window = words[start : start + max_tokens]
            if window:
                chunks.append(" ".join(window))
        return chunks

    chunks: list[str] = []
    buffer: list[str] = []
    for sentence in sentences:
        candidate = "\n".join(buffer + [sentence]) if buffer else sentence
        if estimate_token_count(candidate) > max_tokens and buffer:
            chunks.append("\n".join(buffer))
            buffer = [sentence]
        else:
            buffer.append(sentence)
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks


def _collect_overlap(paragraphs: Iterable[str], overlap_tokens: int) -> list[str]:
    collected: list[str] = []
    total = 0
    for paragraph in reversed(list(paragraphs)):
        token_count = estimate_token_count(paragraph)
        if not collected or total < overlap_tokens:
            collected.insert(0, paragraph)
            total += token_count
        else:
            break
    return collected


def chunk_document(
    document: DocumentRecord,
    normalized_text: str,
    *,
    max_tokens: int = 650,
    overlap_tokens: int = 80,
    min_tokens: int = 40,
) -> list[ChunkRecord]:
    """Split a normalized document into retrieval-friendly chunks."""

    paragraphs: list[str] = []
    for paragraph in _split_paragraphs(normalized_text):
        paragraphs.extend(_split_long_paragraph(paragraph, max_tokens=max_tokens))

    title = (document.title or "").strip()
    chunks: list[ChunkRecord] = []
    buffer: list[str] = []
    current_tokens = 0
    chunk_order = 0

    def flush(force: bool = False) -> None:
        nonlocal buffer, current_tokens, chunk_order
        if not buffer:
            return
        body = "\n\n".join(part for part in buffer if part.strip()).strip()
        if not body:
            buffer = []
            current_tokens = 0
            return
        body_tokens = estimate_token_count(body)
        if body_tokens < min_tokens and not force and chunks:
            return
        chunk_text = f"{title}\n\n{body}" if title else body
        chunks.append(
            ChunkRecord(
                chunk_id=f"{document.document_id}::chunk::{chunk_order}",
                document_id=document.document_id,
                chunk_text=chunk_text,
                chunk_order=chunk_order,
                token_count=estimate_token_count(chunk_text),
                source_type=document.source_type,
                category=document.category,
            )
        )
        overlap = _collect_overlap(buffer, overlap_tokens=overlap_tokens)
        buffer = overlap
        current_tokens = sum(estimate_token_count(part) for part in overlap)
        chunk_order += 1

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph_tokens = estimate_token_count(paragraph)
        should_flush = buffer and (
            current_tokens + paragraph_tokens > max_tokens
            or (_is_heading(paragraph) and current_tokens >= min_tokens)
        )
        if should_flush:
            flush()
            if buffer and current_tokens + paragraph_tokens > max_tokens:
                flush(force=True)

        buffer.append(paragraph)
        current_tokens += paragraph_tokens

    flush(force=True)

    if not chunks and normalized_text.strip():
        text = f"{title}\n\n{normalized_text.strip()}" if title else normalized_text.strip()
        chunks.append(
            ChunkRecord(
                chunk_id=f"{document.document_id}::chunk::0",
                document_id=document.document_id,
                chunk_text=text,
                chunk_order=0,
                token_count=estimate_token_count(text),
                source_type=document.source_type,
                category=document.category,
            )
        )

    return chunks
