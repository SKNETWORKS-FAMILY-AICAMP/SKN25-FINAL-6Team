"""Rechunk article-style policy/terms documents in test_documents_chunks only.

This is intentionally chunk-only: it rewrites test_documents_chunks for
documents whose raw_content has Korean article headings such as "제30조 면책 조항".
Embeddings for affected documents are deleted to avoid stale vectors.
Regenerate test_documents_embeddings_small/large after reviewing the chunks.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "common-python" / "src"))

from common.db.connection import db_connection  # noqa: E402


MAX_CHARS = 2200
TARGET_MAX_CHARS = 1800
MAX_NUMBERED_ITEMS_PER_CHUNK = 6

ARTICLE_HEADING_RE = re.compile(r"(?m)^제\s*\d+\s*조[^\n]*$")
NUMBERED_ITEM_RE = re.compile(r"(?m)^\d+\)\s+")
TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+|[^\s]")


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    source_type: str | None
    category: str | None
    raw_content: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    chunk_text: str
    chunk_order: int
    token_count: int


def estimate_token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_article_blocks(text: str) -> list[str]:
    matches = list(ARTICLE_HEADING_RE.finditer(text))
    if not matches:
        return [text.strip()] if text.strip() else []

    blocks: list[str] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            blocks.append(preamble)

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end].strip()
        if block:
            blocks.append(block)
    return blocks


def article_heading(block: str) -> str:
    first_line = block.splitlines()[0].strip()
    return first_line if ARTICLE_HEADING_RE.match(first_line) else ""


def split_numbered_items(article_block: str) -> tuple[str, list[str]]:
    heading = article_heading(article_block)
    body = article_block[len(heading) :].strip() if heading else article_block.strip()
    matches = list(NUMBERED_ITEM_RE.finditer(body))
    if not matches:
        return heading, [body] if body else []

    intro = body[: matches[0].start()].strip()
    items: list[str] = []
    if intro:
        items.append(intro)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        item = body[match.start() : end].strip()
        if item:
            items.append(item)
    return heading, items


def split_long_item(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) <= 1:
        return [text[start : start + TARGET_MAX_CHARS].strip() for start in range(0, len(text), TARGET_MAX_CHARS)]

    chunks: list[str] = []
    buffer: list[str] = []
    for paragraph in paragraphs:
        candidate = "\n\n".join([*buffer, paragraph]).strip() if buffer else paragraph
        if len(candidate) > TARGET_MAX_CHARS and buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer = [paragraph]
        else:
            buffer.append(paragraph)
    if buffer:
        chunks.append("\n\n".join(buffer).strip())
    return chunks


def split_article_block(block: str) -> list[str]:
    heading = article_heading(block)
    heading, items = split_numbered_items(block)
    numbered_items = [item for item in items if re.match(r"^\d+\)\s+", item)]
    if len(block) <= MAX_CHARS and len(numbered_items) <= MAX_NUMBERED_ITEMS_PER_CHUNK:
        return [block]

    if not items:
        return split_long_item(block)

    chunks: list[str] = []
    buffer: list[str] = []
    numbered_count = 0

    def current_text(parts: list[str]) -> str:
        body = "\n\n".join(part for part in parts if part.strip()).strip()
        return f"{heading}\n\n{body}".strip() if heading else body

    def is_numbered(item: str) -> bool:
        return bool(re.match(r"^\d+\)\s+", item))

    def flush() -> None:
        nonlocal buffer, numbered_count
        if not buffer:
            return
        text = current_text(buffer)
        if len(text) > MAX_CHARS:
            chunks.extend(split_long_item(text))
        else:
            chunks.append(text)
        buffer = []
        numbered_count = 0

    for item in items:
        candidate_numbered_count = numbered_count + (1 if is_numbered(item) else 0)
        candidate = current_text([*buffer, item]) if buffer else current_text([item])
        should_flush = buffer and (
            len(candidate) > TARGET_MAX_CHARS
            or candidate_numbered_count > MAX_NUMBERED_ITEMS_PER_CHUNK
        )
        if should_flush:
            flush()
        buffer.append(item)
        numbered_count += 1 if is_numbered(item) else 0

    flush()
    return chunks


def rechunk_document(document: Document) -> list[Chunk]:
    normalized = normalize_text(document.raw_content)
    blocks = split_article_blocks(normalized)
    pieces: list[str] = []
    for block in blocks:
        pieces.extend(split_article_block(block))

    chunks: list[Chunk] = []
    for order, piece in enumerate(piece for piece in pieces if piece.strip()):
        chunk_text = f"{document.title}\n\n{piece.strip()}" if document.title else piece.strip()
        chunks.append(
            Chunk(
                chunk_id=f"{document.document_id}::chunk::{order}",
                document_id=document.document_id,
                chunk_text=chunk_text,
                chunk_order=order,
                token_count=estimate_token_count(chunk_text),
            )
        )
    return chunks


def load_documents(document_id: str | None) -> list[Document]:
    clauses = ["source_type = 'hoyoverse_policy'", "raw_content ~ '(^|\\n)제\\s*[0-9]+\\s*조'"]
    params: list[str] = []
    if document_id:
        clauses.append("documents_id = %s")
        params.append(document_id)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT documents_id AS document_id, title, source_type, category, raw_content
                FROM documents
                WHERE {" AND ".join(clauses)}
                ORDER BY documents_id
                """,
                tuple(params),
            )
            return [Document(**row) for row in cur.fetchall()]


def persist_chunks_only(document: Document, chunks: list[Chunk]) -> None:
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                for table in ("test_documents_embeddings", "test_documents_embeddings_small", "test_documents_embeddings_large"):
                    cur.execute(
                        f"""
                        DELETE FROM {table} e
                        USING test_documents_chunks c
                        WHERE e.chunk_id = c.chunk_id
                          AND c.document_id = %s
                        """,
                        (document.document_id,),
                    )
                cur.execute("DELETE FROM test_documents_chunks WHERE document_id = %s", (document.document_id,))
                cur.executemany(
                    """
                    INSERT INTO test_documents_chunks (chunk_id, document_id, chunk_text, chunk_order, token_count)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [(c.chunk_id, c.document_id, c.chunk_text, c.chunk_order, c.token_count) for c in chunks],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv(".env", override=True)
    documents = load_documents(args.document_id)
    print(f"documents={len(documents)}")

    for document in documents:
        chunks = rechunk_document(document)
        print(f"{document.document_id}\t{document.title}\tchunks={len(chunks)}\tmax_chars={max(len(c.chunk_text) for c in chunks)}")
        for chunk in chunks:
            if document.document_id == "HYV-TER-1" and "제30조 면책 조항" in chunk.chunk_text:
                sample = chunk.chunk_text.replace("\n", " ")[:500]
                print(f"  {chunk.chunk_id}\torder={chunk.chunk_order}\tchars={len(chunk.chunk_text)}\ttokens={chunk.token_count}\t{sample}")
        if args.apply:
            persist_chunks_only(document, chunks)
            print(f"persisted_chunks_only={document.document_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
