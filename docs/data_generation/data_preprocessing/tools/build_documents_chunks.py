"""Build documents_chunks from documents.

Default mode is dry-run. Use --apply to rewrite documents_chunks and delete
stale document embeddings for the affected documents.

Use --with-embeddings with --apply to generate and insert documents_embeddings
with text-embedding-3-small, 1536 dimensions.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from psycopg.rows import dict_row


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "common-python" / "src"))

from common.db.connection import db_connection  # noqa: E402
from common.documents_processing.types import ChunkRecord  # noqa: E402


TARGET_MAX_CHARS = 1600
MAX_CHARS = 2200
MAX_ROMAN_ITEMS = 5
MAX_TABLE_ROWS = 5
MAX_TERMS_ITEMS_PER_CHUNK = 6
EMBEDDING_DIMENSIONS = 1536
SMALL_EMBEDDING_MODEL = "text-embedding-3-small"
LARGE_EMBEDDING_MODEL = "text-embedding-3-large"

TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+|[^\s]")
QA_RE = re.compile(r"(?ms)(?:^|\n)\s*질문\s*[:：]\s*(.*?)\s+답변\s*[:：]\s*(.*?)(?=(?:\n\s*질문\s*[:：])|\Z)")
SECTION_RE = re.compile(r"(?m)^([1-9]|1[0-3])\.\s+(.+)$")
TOKEN_RE = re.compile(r"[\uac00-\ud7a3]+|[A-Za-z0-9_]+|[^\s]")
QA_RE = re.compile(
    r"(?ms)(?:^|\n|\?{2,})\s*\uc9c8\ubb38\s*[:\uff1a]\s*(.*?)\s*(?:\n|\?{2,})+\s*\ub2f5\ubcc0\s*[:\uff1a]\s*(.*?)(?=(?:\n|\?{2,})+\s*\uc9c8\ubb38\s*[:\uff1a]|\Z)"
)
INNER_QA_RE = re.compile(
    r"(?ms)(?:^|\n|\?{2,})\s*Q\s*[:.\uff1a]\s*(.*?)\s*(?:\n|\?{2,})+\s*A\s*[:.\uff1a]\s*(.*?)(?=(?:\n|\?{2,})+\s*Q\s*[:.\uff1a]|\Z)"
)
LETTER_RE = re.compile(r"(?m)^([A-Z])\.\s+(.+)$")
ROMAN_RE = re.compile(r"(?m)^([ivxlcdm]+)\.\s+(.+)$")
TABLE_RE = re.compile(r"(?m)^## Table\s+(\d+)\s*$")
ARTICLE_HEADING_RE = re.compile(r"(?m)^제\s*\d+\s*조[^\n]*$")
NUMBERED_ITEM_RE = re.compile(r"(?m)^\d+\)\s+")
NOTICE_HEADER_RE = re.compile(r"(?m)^=+\s*([^=\n]+?)\s*=+$")
NOTICE_SUBHEADER_RE = re.compile(r"(?m)^(?:[●◆◇▌]\s*[^\n]+|\d+\.\s+[^\n]+)$")

PRIVACY_BODY_START = "1. 수집 및 처리하는 데이터의 유형"
PRIVACY_TABLES_START = "[Extracted Tables]"
PRIVACY_TOC_START = "본 개인정보처리방침에서 안내하는 내용은 다음과 같습니다."


@dataclass(frozen=True)
class Document:
    document_id: str
    source_type: str | None
    category: str | None
    title: str
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


def prefixed(title: str, body: str) -> str:
    body = body.strip()
    title = title.strip()
    return f"{title}\n\n{body}".strip() if title and not body.startswith(title) else body


def with_section_prefix(title: str, section_path: str, headings: list[str], body: str) -> str:
    lines = [title.strip()]
    if section_path:
        lines.append(f"Section: {section_path}")
    lines.extend(heading.strip() for heading in headings if heading.strip())
    head = "\n".join(lines).strip()
    body = body.strip()
    return f"{head}\n\n{body}".strip() if body else head


def split_plain_text(text: str, max_chars: int = TARGET_MAX_CHARS) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    buffer: list[str] = []

    for paragraph in paragraphs:
        candidate = "\n\n".join([*buffer, paragraph]).strip() if buffer else paragraph
        if len(candidate) > max_chars and buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer = [paragraph]
        elif len(paragraph) > MAX_CHARS:
            if buffer:
                chunks.append("\n\n".join(buffer).strip())
                buffer = []
            chunks.extend(paragraph[start : start + max_chars].strip() for start in range(0, len(paragraph), max_chars))
        else:
            buffer.append(paragraph)

    if buffer:
        chunks.append("\n\n".join(buffer).strip())
    return [chunk for chunk in chunks if chunk]


def split_by_matches(text: str, matches: list[re.Match[str]]) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), match.group(2).strip(), text[match.start() : end].strip()))
    return blocks


def is_low_info_weapon_doc(document: Document) -> bool:
    title = document.title or ""
    raw = document.raw_content or ""
    return (
        len(raw.strip()) < 180
        and ("신규 무기 안내" in title or "신규 장비 안내" in title)
        and ("Lv.90" in raw or "재련 1단계" in raw)
    )


def rechunk_qna(document: Document) -> list[str]:
    pairs = []
    for match in QA_RE.finditer(document.raw_content):
        question = " ".join(match.group(1).split())
        answer = match.group(2).strip()
        if question and answer:
            pairs.append((question, answer))

    if not pairs:
        return [prefixed(document.title, piece) for piece in split_plain_text(document.raw_content)]

    texts: list[str] = []
    for question, answer in pairs:
        body = f"질문: {question}\n\n답변:\n{answer}"
        if len(body) <= MAX_CHARS:
            texts.append(body)
        else:
            pieces = split_plain_text(answer)
            for index, piece in enumerate(pieces):
                suffix = f" ({index + 1}/{len(pieces)})" if len(pieces) > 1 else ""
                texts.append(f"질문: {question}{suffix}\n\n답변:\n{piece}")
    return texts


def split_privacy_document_parts(raw: str) -> tuple[str, str, str]:
    text = normalize_text(raw)
    tables_index = text.find(PRIVACY_TABLES_START)
    main_text = text if tables_index < 0 else text[:tables_index].strip()
    tables_text = "" if tables_index < 0 else text[tables_index:].strip()

    body_match = SECTION_RE.search(main_text)
    if not body_match:
        return main_text, "", tables_text
    body_index = body_match.start()

    preamble = main_text[:body_index].strip()
    toc_index = preamble.find(PRIVACY_TOC_START)
    if toc_index >= 0:
        preamble = preamble[:toc_index].strip()
    body = main_text[body_index:].strip()
    return preamble, body, tables_text


def split_roman_items(text: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(ROMAN_RE.finditer(text))
    if not matches:
        return text.strip(), []
    intro = text[: matches[0].start()].strip()
    items = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        items.append((match.group(1), text[match.start() : end].strip()))
    return intro, items


def roman_range_label(items: list[tuple[str, str]]) -> str:
    first = items[0][0]
    last = items[-1][0]
    return first if first == last else f"{first}~{last}"


def group_roman_items(items: list[tuple[str, str]], title: str, section_path: str, headings: list[str]) -> list[tuple[str, str]]:
    groups: list[tuple[str, str]] = []
    buffer: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        label = roman_range_label(buffer)
        path = f"{section_path}-{label}"
        groups.append((path, "\n\n".join(item_text for _, item_text in buffer)))
        buffer = []

    for item in items:
        candidate = [*buffer, item]
        label = roman_range_label(candidate)
        path = f"{section_path}-{label}"
        body = "\n\n".join(item_text for _, item_text in candidate)
        candidate_text = with_section_prefix(title, path, headings, body)
        if buffer and (len(candidate_text) > TARGET_MAX_CHARS or len(candidate) > MAX_ROMAN_ITEMS):
            flush()
        buffer.append(item)
    flush()
    return groups


def split_letter_blocks(section_body: str) -> tuple[str, list[tuple[str, str, str]]]:
    matches = list(LETTER_RE.finditer(section_body))
    if not matches:
        return section_body.strip(), []
    intro = section_body[: matches[0].start()].strip()
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section_body)
        blocks.append((match.group(1), match.group(2).strip(), section_body[match.start() : end].strip()))
    return intro, blocks


def strip_section13_inline_tables(section_body: str) -> str:
    markers = [
        ("사용 목적\n\n개인정보 유형", "데이터 저장"),
        ("아동의 개인 정보\n\n수집 목적", "이용자가 로그인하거나"),
        ("수집 경로\n\n수집하는 영구 식별자", "(v) 데이터 공유"),
        ("데이터 수신자의 이름 또는 범주", "(c) 캘리포니아주"),
        ("서버 위치", "COGNOSPHERE PTE. LTD."),
    ]
    cleaned = section_body
    for start_marker, end_marker in markers:
        start = cleaned.find(start_marker)
        end = cleaned.find(end_marker, start + len(start_marker)) if start >= 0 else -1
        if start >= 0 and end >= 0:
            cleaned = cleaned[:start] + "\n\n" + cleaned[end:]
    return normalize_text(cleaned)


def rechunk_privacy(document: Document) -> list[str]:
    preamble, body, tables = split_privacy_document_parts(document.raw_content)
    texts: list[str] = []
    if preamble:
        texts.extend(with_section_prefix(document.title, "intro", [], piece) for piece in split_plain_text(preamble))

    for section_number, section_title, section_block in split_by_matches(body, list(SECTION_RE.finditer(body))):
        section_heading = f"{section_number}. {section_title}"
        section_body = section_block[len(section_heading) :].strip()
        if section_number == "13":
            section_body = strip_section13_inline_tables(section_body)
        section_intro, letter_blocks = split_letter_blocks(section_body)
        section_path = section_number

        if section_intro:
            intro, roman_items = split_roman_items(section_intro)
            if roman_items:
                if intro:
                    texts.append(with_section_prefix(document.title, section_path, [section_heading], intro))
                for path, item_body in group_roman_items(roman_items, document.title, section_path, [section_heading]):
                    texts.append(with_section_prefix(document.title, path, [section_heading], item_body))
            else:
                texts.extend(
                    with_section_prefix(document.title, section_path, [section_heading], piece)
                    for piece in split_plain_text(section_intro)
                )

        for letter, letter_title, letter_block in letter_blocks:
            letter_heading = f"{letter}. {letter_title}"
            letter_body = letter_block[len(letter_heading) :].strip()
            letter_path = f"{section_number}-{letter}"
            intro, roman_items = split_roman_items(letter_body)
            if roman_items:
                if intro:
                    texts.append(with_section_prefix(document.title, letter_path, [section_heading, letter_heading], intro))
                for path, item_body in group_roman_items(
                    roman_items, document.title, letter_path, [section_heading, letter_heading]
                ):
                    texts.append(with_section_prefix(document.title, path, [section_heading, letter_heading], item_body))
            else:
                texts.extend(
                    with_section_prefix(document.title, letter_path, [section_heading, letter_heading], piece)
                    for piece in split_plain_text(letter_body)
                )

    texts.extend(build_privacy_table_chunks(document.title, tables))
    return [text for text in texts if text.strip()]


def build_privacy_table_chunks(title: str, tables_text: str) -> list[str]:
    if not tables_text:
        return []
    texts: list[str] = []
    matches = list(TABLE_RE.finditer(tables_text))
    for index, match in enumerate(matches):
        table_number = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tables_text)
        table_block = tables_text[match.end() : end].strip()
        rows = [line.strip() for line in table_block.splitlines() if line.strip().startswith("|")]
        non_rows = [line.strip() for line in table_block.splitlines() if line.strip() and not line.strip().startswith("|")]
        if len(rows) <= 2:
            continue
        header = [*non_rows, *rows[:2]]
        data_rows = [row for row in rows[2:] if row.replace("|", "").strip()]
        for start in range(0, len(data_rows), MAX_TABLE_ROWS):
            chunk_rows = data_rows[start : start + MAX_TABLE_ROWS]
            row_label = f"row{start + 1}~{start + len(chunk_rows)}"
            section_path = f"table-{table_number}-{row_label}"
            body = "\n".join([*header, *chunk_rows]).strip()
            texts.append(with_section_prefix(title, section_path, [f"Table {table_number}"], body))
    return texts


def split_article_blocks(text: str) -> list[str]:
    matches = list(ARTICLE_HEADING_RE.finditer(text))
    if not matches:
        return [text.strip()] if text.strip() else []
    blocks = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            blocks.append(preamble)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(text[match.start() : end].strip())
    return [block for block in blocks if block]


def split_terms_numbered_items(article_block: str) -> tuple[str, list[str]]:
    heading = article_block.splitlines()[0].strip() if ARTICLE_HEADING_RE.match(article_block.splitlines()[0].strip()) else ""
    body = article_block[len(heading) :].strip() if heading else article_block.strip()
    matches = list(NUMBERED_ITEM_RE.finditer(body))
    if not matches:
        return heading, [body] if body else []
    intro = body[: matches[0].start()].strip()
    items = [intro] if intro else []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        items.append(body[match.start() : end].strip())
    return heading, [item for item in items if item]


def rechunk_terms(document: Document) -> list[str]:
    texts: list[str] = []
    for block in split_article_blocks(normalize_text(document.raw_content)):
        heading, items = split_terms_numbered_items(block)
        numbered_items = [item for item in items if NUMBERED_ITEM_RE.match(item)]
        if len(block) <= MAX_CHARS and len(numbered_items) <= MAX_TERMS_ITEMS_PER_CHUNK:
            texts.append(prefixed(document.title, block))
            continue

        if not items:
            texts.extend(prefixed(document.title, piece) for piece in split_plain_text(block))
            continue

        buffer: list[str] = []
        numbered_count = 0

        def make_text(parts: list[str]) -> str:
            body = "\n\n".join(part for part in parts if part.strip()).strip()
            return f"{heading}\n\n{body}".strip() if heading else body

        def flush() -> None:
            nonlocal buffer, numbered_count
            if not buffer:
                return
            text = make_text(buffer)
            if len(text) > MAX_CHARS:
                texts.extend(prefixed(document.title, piece) for piece in split_plain_text(text))
            else:
                texts.append(prefixed(document.title, text))
            buffer = []
            numbered_count = 0

        for item in items:
            item_numbered = bool(NUMBERED_ITEM_RE.match(item))
            candidate_count = numbered_count + (1 if item_numbered else 0)
            candidate = make_text([*buffer, item])
            if buffer and (len(candidate) > TARGET_MAX_CHARS or candidate_count > MAX_TERMS_ITEMS_PER_CHUNK):
                flush()
            buffer.append(item)
            numbered_count += 1 if item_numbered else 0
        flush()

    return [text for text in texts if text.strip()]


def split_notice_sections(text: str) -> list[str]:
    matches = list(NOTICE_HEADER_RE.finditer(text))
    if not matches:
        return split_plain_text(text)

    sections: list[str] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.extend(split_plain_text(preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end].strip()
        if len(block) <= MAX_CHARS:
            sections.append(block)
        else:
            sections.extend(split_notice_subsections(block))
    return sections


def split_notice_subsections(block: str) -> list[str]:
    header = block.splitlines()[0].strip()
    body = block[len(header) :].strip()
    matches = list(NOTICE_SUBHEADER_RE.finditer(body))
    if not matches:
        return split_plain_text(block)

    chunks: list[str] = []
    intro = body[: matches[0].start()].strip()
    if intro:
        chunks.extend(split_plain_text(f"{header}\n\n{intro}"))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sub_block = f"{header}\n\n{body[match.start() : end].strip()}"
        if len(sub_block) <= MAX_CHARS:
            chunks.append(sub_block)
        else:
            chunks.extend(split_plain_text(sub_block))
    return chunks


def rechunk_notice_or_guide(document: Document) -> list[str]:
    pieces = split_notice_sections(normalize_text(document.raw_content)) if document.source_type == "naver_cafe_notice" else split_plain_text(normalize_text(document.raw_content))
    return [prefixed(document.title, piece) for piece in pieces if piece.strip()]


def rechunk_qna(document: Document) -> list[str]:
    pairs: list[tuple[str, str]] = []
    for match in QA_RE.finditer(document.raw_content):
        outer_question = " ".join(match.group(1).split())
        answer = match.group(2).strip()
        inner_pairs = [
            (" ".join(inner.group(1).split()), inner.group(2).strip())
            for inner in INNER_QA_RE.finditer(answer)
            if inner.group(1).strip() and inner.group(2).strip()
        ]
        if inner_pairs:
            pairs.extend(inner_pairs)
        elif outer_question and answer:
            pairs.append((outer_question, answer))

    if not pairs:
        pairs.extend(
            (" ".join(match.group(1).split()), match.group(2).strip())
            for match in INNER_QA_RE.finditer(document.raw_content)
            if match.group(1).strip() and match.group(2).strip()
        )

    if not pairs:
        return [prefixed(document.title, piece) for piece in split_plain_text(document.raw_content)]

    texts: list[str] = []
    prefix_text = (document.category or "").strip() if document.document_id.startswith("QNA-COM-") else document.title.strip()
    for question, answer in pairs:
        body_parts = []
        if prefix_text:
            body_parts.append(prefix_text)
        body_parts.append(f"\uc9c8\ubb38: {question}")
        body_parts.append(f"\ub2f5\ubcc0:\n{answer}")
        body = "\n\n".join(body_parts)
        if len(body) <= MAX_CHARS:
            texts.append(body)
        else:
            pieces = split_plain_text(answer)
            for index, piece in enumerate(pieces):
                suffix = f" ({index + 1}/{len(pieces)})" if len(pieces) > 1 else ""
                split_parts = []
                if prefix_text:
                    split_parts.append(prefix_text)
                split_parts.append(f"\uc9c8\ubb38: {question}{suffix}")
                split_parts.append(f"\ub2f5\ubcc0:\n{piece}")
                texts.append("\n\n".join(split_parts))
    return texts


def rechunk_document(document: Document) -> list[Chunk]:
    if is_low_info_weapon_doc(document):
        return []

    source_type = document.source_type or ""
    category = document.category or ""
    is_qna_source = source_type.startswith("universe_qna") or document.document_id.startswith("QNA-")
    is_notice_qa = (
        source_type == "naver_cafe_notice"
        and document.document_id.startswith("NVC-NOT-")
        and "개발진 간담회" not in document.title
        and len(INNER_QA_RE.findall(document.raw_content)) >= 2
    )
    if is_qna_source or is_notice_qa:
        texts = rechunk_qna(document)
    elif source_type == "universe_policy" and category == "privacy":
        texts = rechunk_privacy(document)
    elif source_type == "universe_policy" and category == "terms":
        texts = rechunk_terms(document)
    elif source_type in {"naver_cafe_notice", "naver_cafe_guide"}:
        texts = rechunk_notice_or_guide(document)
    else:
        texts = [prefixed(document.title, piece) for piece in split_plain_text(normalize_text(document.raw_content))]

    chunks: list[Chunk] = []
    for order, text in enumerate(text for text in texts if text.strip()):
        chunks.append(
            Chunk(
                chunk_id=f"{document.document_id}::chunk::{order}",
                document_id=document.document_id,
                chunk_text=text.strip(),
                chunk_order=order,
                token_count=estimate_token_count(text),
            )
        )
    return chunks


def to_chunk_record(chunk: Chunk, document: Document) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        chunk_text=chunk.chunk_text,
        chunk_order=chunk.chunk_order,
        token_count=chunk.token_count,
        source_type=document.source_type,
        category=document.category,
    )


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def embed_chunk_records(
    chunks: list[ChunkRecord],
    model: str,
    *,
    dimensions: int | None,
    model_label: str,
) -> list[tuple[str, str, str, str, str | None, str | None]]:
    if not chunks:
        return []
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is required to generate embeddings")
    kwargs = {"model": model, "api_key": api_key}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    embedder = OpenAIEmbeddings(**kwargs)
    vectors = embedder.embed_documents([chunk.chunk_text for chunk in chunks])
    return [
        (
            f"{chunk.chunk_id}::embedding::{model_label}",
            chunk.chunk_id,
            vector_literal(list(vector)),
            model_label,
            chunk.source_type,
            chunk.category,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def load_documents(document_id: str | None = None, document_prefix: str | None = None) -> list[Document]:
    where = ["COALESCE(BTRIM(raw_content), '') <> ''"]
    params: list[str] = []
    if document_id:
        where.append("documents_id = %s")
        params.append(document_id)
    if document_prefix:
        where.append("documents_id LIKE %s")
        params.append(f"{document_prefix}%")

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    documents_id AS document_id,
                    source_type,
                    category,
                    COALESCE(title, '') AS title,
                    raw_content
                FROM documents
                WHERE {" AND ".join(where)}
                ORDER BY documents_id
                """,
                tuple(params),
            )
            return [Document(**row) for row in cur.fetchall()]


def persist_chunks(
    chunks: list[Chunk],
    chunk_records: list[ChunkRecord],
    embeddings,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
) -> None:
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                if document_id or document_ids:
                    affected_document_ids = [document_id] if document_id else list(document_ids or [])
                    cur.execute(
                        """
                        DELETE FROM documents_embeddings e
                        USING documents_chunks c
                        WHERE e.chunk_id = c.chunk_id
                          AND c.document_id = ANY(%s)
                        """,
                        (affected_document_ids,),
                    )
                    cur.execute("DELETE FROM documents_chunks WHERE document_id = ANY(%s)", (affected_document_ids,))
                else:
                    cur.execute("DELETE FROM documents_embeddings")
                    cur.execute("DELETE FROM documents_chunks")

                cur.executemany(
                    """
                    INSERT INTO documents_chunks (chunk_id, document_id, chunk_text, chunk_order, token_count)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [(c.chunk_id, c.document_id, c.chunk_text, c.chunk_order, c.token_count) for c in chunks],
                )
                if embeddings:
                    cur.executemany(
                        """
                        INSERT INTO documents_embeddings (
                            embedding_id, chunk_id, embedding_vector, embedding_model, source_type, category
                        )
                        VALUES (%s, %s, %s::vector, %s, %s, %s)
                        """,
                        embeddings,
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def print_stats(chunks_by_doc: dict[str, list[Chunk]], skipped_docs: list[str]) -> None:
    all_chunks = [chunk for chunks in chunks_by_doc.values() for chunk in chunks]
    print(f"documents={len(chunks_by_doc) + len(skipped_docs)}")
    print(f"skipped_low_info_docs={len(skipped_docs)}")
    print(f"chunks={len(all_chunks)}")
    if not all_chunks:
        return
    lengths = [len(chunk.chunk_text) for chunk in all_chunks]
    print(f"min_chars={min(lengths)}")
    print(f"max_chars={max(lengths)}")
    print(f"lt120={sum(1 for length in lengths if length < 120)}")
    print(f"gt2200={sum(1 for length in lengths if length > 2200)}")

    print("\nsample:")
    for chunk in all_chunks[:12]:
        sample = chunk.chunk_text.replace("\n", " ")[:260]
        print(f"- {chunk.chunk_id} order={chunk.chunk_order} chars={len(chunk.chunk_text)} tokens={chunk.token_count} {sample}")

    if skipped_docs:
        print("\nskipped_low_info_doc_ids:")
        print(", ".join(skipped_docs[:80]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id")
    parser.add_argument("--document-prefix")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Generate and insert documents_embeddings.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env", override=True)
    documents = load_documents(args.document_id, args.document_prefix)
    chunks_by_doc: dict[str, list[Chunk]] = {}
    skipped_docs: list[str] = []

    for document in documents:
        chunks = rechunk_document(document)
        if not chunks and is_low_info_weapon_doc(document):
            skipped_docs.append(document.document_id)
            continue
        chunks_by_doc[document.document_id] = chunks

    print_stats(chunks_by_doc, skipped_docs)

    if args.apply:
        all_chunks = [chunk for chunks in chunks_by_doc.values() for chunk in chunks]
        docs_by_id = {document.document_id: document for document in documents}
        chunk_records = [to_chunk_record(chunk, docs_by_id[chunk.document_id]) for chunk in all_chunks]
        embeddings = []
        if args.with_embeddings:
            embeddings = embed_chunk_records(
                chunk_records,
                SMALL_EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS,
                model_label=f"{SMALL_EMBEDDING_MODEL}:1536",
            )
            print(f"generated_embeddings={len(embeddings)}")
        else:
            print("generated_embeddings=0")
            print("note=document embedding rows will be cleared for affected documents")
        persist_chunks(
            all_chunks,
            chunk_records,
            embeddings,
            args.document_id,
            [document.document_id for document in documents] if args.document_prefix else None,
        )
        print("\napplied=true")
    else:
        print("\ndry_run=true")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
