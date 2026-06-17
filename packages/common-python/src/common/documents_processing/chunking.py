"""Chunking helpers for document search and embedding generation."""

from __future__ import annotations

import re
from typing import Iterable

from .types import ChunkRecord, DocumentRecord


TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+|[^\s]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_DEFAULT_CHUNK_PROFILE = {"max_tokens": 650, "overlap_tokens": 80, "min_tokens": 40}
_SOURCE_TYPE_CHUNK_PROFILES = {
    "hoyoverse_qna_common": {"max_tokens": 420, "overlap_tokens": 60, "min_tokens": 20},
    "hoyoverse_qna_onlygenshin": {"max_tokens": 420, "overlap_tokens": 60, "min_tokens": 20},
    "hoyoverse_policy": {"max_tokens": 800, "overlap_tokens": 120, "min_tokens": 80},
    "naver_cafe_guide": {"max_tokens": 700, "overlap_tokens": 100, "min_tokens": 50},
    "naver_cafe_notice": {"max_tokens": 550, "overlap_tokens": 80, "min_tokens": 30},
}
_QA_BLOCK_RE = re.compile(
    r"(?ms)(?:^|\n)\s*질문\s*[:：]\s*(.*?)\s+"
    r"답변\s*[:：]\s*(.*?)(?=(?:\n\s*질문\s*[:：])|\Z)"
)
_INNER_QA_BLOCK_RE = re.compile(
    r"(?ms)(?:^|\n)\s*Q\s*[:：]\s*(.*?)\s+"
    r"A\s*[:：]\s*(.*?)(?=(?:\n\s*Q\s*[:：])|\Z)"
)


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


def _chunk_profile_for_source_type(source_type: str | None) -> dict[str, int]:
    profile = dict(_DEFAULT_CHUNK_PROFILE)
    profile.update(_SOURCE_TYPE_CHUNK_PROFILES.get(str(source_type or ""), {}))
    return profile


def _split_qa_blocks(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in _QA_BLOCK_RE.finditer(text):
        question = " ".join(match.group(1).split())
        answer = match.group(2).strip()
        if not question or not answer:
            continue

        inner_pairs = _split_inner_qa_blocks(answer)
        if inner_pairs:
            pairs.extend(inner_pairs)
        else:
            pairs.append((question, answer))
    return pairs


def _split_inner_qa_blocks(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in _INNER_QA_BLOCK_RE.finditer(text):
        question = " ".join(match.group(1).split())
        answer = match.group(2).strip()
        if question and answer:
            pairs.append((question, answer))
    return pairs


def _chunk_qa_blocks(
    document: DocumentRecord,
    qa_pairs: list[tuple[str, str]],
    *,
    max_tokens: int,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    title = (document.title or "").strip()
    for index, (question, answer) in enumerate(qa_pairs):
        qa_parts = []
        if title:
            qa_parts.append(title)
        qa_parts.extend([f"질문: {question}", f"답변:\n{answer}"])
        qa_text = "\n\n".join(qa_parts).strip()
        pieces = _split_long_paragraph(qa_text, max_tokens=max_tokens)
        if not pieces:
            pieces = [qa_text]
        for piece_index, piece in enumerate(pieces):
            chunk_order = len(chunks)
            suffix = f"::part::{piece_index}" if len(pieces) > 1 else ""
            chunk_text = piece.strip()
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document.document_id}::chunk::{chunk_order}{suffix}",
                    document_id=document.document_id,
                    chunk_text=chunk_text,
                    chunk_order=chunk_order,
                    token_count=estimate_token_count(chunk_text),
                    source_type=document.source_type,
                    category=document.category,
                )
            )
    return chunks


def chunk_document(
    document: DocumentRecord,
    normalized_text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    min_tokens: int | None = None,
) -> list[ChunkRecord]:
    """Split a normalized document into retrieval-friendly chunks."""

    profile = _chunk_profile_for_source_type(document.source_type)
    max_tokens = max_tokens or profile["max_tokens"]
    overlap_tokens = overlap_tokens or profile["overlap_tokens"]
    min_tokens = min_tokens or profile["min_tokens"]

    qa_pairs = _split_qa_blocks(normalized_text)
    if qa_pairs:
        return _chunk_qa_blocks(document, qa_pairs, max_tokens=max_tokens)

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
