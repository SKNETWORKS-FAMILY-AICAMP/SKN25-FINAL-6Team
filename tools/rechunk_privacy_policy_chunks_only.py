"""Rechunk HYV-PRI-1 privacy policy into section-prefixed chunks only.

The output format keeps the document title and the current section path in
front of each chunk, for example:

HoYoverse privacy policy title
Section: 1-A-i~iv
1. ...
A. ...

i. ...
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


DOCUMENT_ID = "HYV-PRI-1"
TARGET_MAX_CHARS = 1600
MAX_CHARS = 2200
MAX_ROMAN_ITEMS = 5
MAX_TABLE_ROWS = 5

SECTION_RE = re.compile(r"(?m)^([1-9]|1[0-3])\.\s+(.+)$")
LETTER_RE = re.compile(r"(?m)^([A-Z])\.\s+(.+)$")
ROMAN_RE = re.compile(r"(?m)^([ivxlcdm]+)\.\s+(.+)$")
TABLE_RE = re.compile(r"(?m)^## Table\s+(\d+)\s*$")
TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+|[^\s]")

BODY_START = "1. \uc218\uc9d1 \ubc0f \ucc98\ub9ac\ud558\ub294 \ub370\uc774\ud130\uc758 \uc720\ud615"
TABLES_START = "[Extracted Tables]"
TOC_START = "\ubcf8 \uac1c\uc778\uc815\ubcf4\ucc98\ub9ac\ubc29\uce68\uc5d0\uc11c \uc548\ub0b4\ud558\ub294 \ub0b4\uc6a9\uc740 \ub2e4\uc74c\uacfc \uac19\uc2b5\ub2c8\ub2e4."


@dataclass(frozen=True)
class Document:
    document_id: str
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


def split_by_matches(text: str, matches: list[re.Match[str]]) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), match.group(2).strip(), text[match.start() : end].strip()))
    return blocks


def split_document_parts(raw: str) -> tuple[str, str, str]:
    text = normalize_text(raw)
    tables_index = text.find(TABLES_START)
    main_text = text if tables_index < 0 else text[:tables_index].strip()
    tables_text = "" if tables_index < 0 else text[tables_index:].strip()

    body_index = main_text.find(BODY_START)
    if body_index < 0:
        return main_text, "", tables_text

    preamble = main_text[:body_index].strip()
    toc_index = preamble.find(TOC_START)
    if toc_index >= 0:
        preamble = preamble[:toc_index].strip()
    body = main_text[body_index:].strip()
    return preamble, body, tables_text


def prefix(title: str, section_path: str, headings: list[str]) -> str:
    lines = [title]
    if section_path:
        lines.append(f"Section: {section_path}")
    lines.extend(heading for heading in headings if heading)
    return "\n".join(lines).strip()


def with_prefix(title: str, section_path: str, headings: list[str], body: str) -> str:
    head = prefix(title, section_path, headings)
    body = body.strip()
    return f"{head}\n\n{body}".strip() if body else head


def split_plain_text(text: str, max_chars: int = TARGET_MAX_CHARS) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
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
    return chunks


def split_roman_items(text: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(ROMAN_RE.finditer(text))
    if not matches:
        return text.strip(), []
    intro = text[: matches[0].start()].strip()
    items: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        items.append((match.group(1), text[match.start() : end].strip()))
    return intro, items


def roman_range_label(items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
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
        body = "\n\n".join(item_text for _, item_text in buffer)
        path = f"{section_path}-{label}" if label else section_path
        groups.append((path, body))
        buffer = []

    for item in items:
        candidate_items = [*buffer, item]
        candidate_label = roman_range_label(candidate_items)
        candidate_path = f"{section_path}-{candidate_label}" if candidate_label else section_path
        candidate_body = "\n\n".join(item_text for _, item_text in candidate_items)
        candidate_text = with_prefix(title, candidate_path, headings, candidate_body)
        if buffer and (len(candidate_text) > TARGET_MAX_CHARS or len(candidate_items) > MAX_ROMAN_ITEMS):
            flush()
        buffer.append(item)
    flush()
    return groups


def split_letter_blocks(section_body: str) -> tuple[str, list[tuple[str, str, str]]]:
    matches = list(LETTER_RE.finditer(section_body))
    if not matches:
        return section_body.strip(), []
    intro = section_body[: matches[0].start()].strip()
    blocks: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section_body)
        blocks.append((match.group(1), match.group(2).strip(), section_body[match.start() : end].strip()))
    return intro, blocks


def build_main_chunks(title: str, preamble: str, body: str) -> list[str]:
    texts: list[str] = []
    if preamble:
        for piece in split_plain_text(preamble):
            texts.append(with_prefix(title, "intro", [], piece))

    section_blocks = split_by_matches(body, list(SECTION_RE.finditer(body)))
    for section_number, section_title, section_block in section_blocks:
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
                    texts.append(with_prefix(title, section_path, [section_heading], intro))
                for path, item_body in group_roman_items(roman_items, title, section_path, [section_heading]):
                    texts.append(with_prefix(title, path, [section_heading], item_body))
            else:
                for piece in split_plain_text(section_intro):
                    texts.append(with_prefix(title, section_path, [section_heading], piece))

        for letter, letter_title, letter_block in letter_blocks:
            letter_heading = f"{letter}. {letter_title}"
            letter_body = letter_block[len(letter_heading) :].strip()
            letter_path = f"{section_number}-{letter}"
            intro, roman_items = split_roman_items(letter_body)
            if roman_items:
                if intro:
                    texts.append(with_prefix(title, letter_path, [section_heading, letter_heading], intro))
                for path, item_body in group_roman_items(roman_items, title, letter_path, [section_heading, letter_heading]):
                    texts.append(with_prefix(title, path, [section_heading, letter_heading], item_body))
            else:
                for piece in split_plain_text(letter_body):
                    texts.append(with_prefix(title, letter_path, [section_heading, letter_heading], piece))

    return texts


def strip_section13_inline_tables(section_body: str) -> str:
    """Drop prose-extracted table bodies that are represented later as tables.

    The privacy policy repeats US special-jurisdiction tables inline as plain
    paragraphs, then repeats them again under "[Extracted Tables]". Keeping both
    makes generic "Section: 13" chunks look like loose table rows. The structured
    table chunks are better for retrieval, so remove the inline copy.
    """

    replacements = [
        ("\n\n사용 목적\n\n개인정보 유형\n\n", "\n\n데이터 저장\n\n"),
        ("\n\n아동의 개인 정보\n\n수집 목적\n\n업무상 보관 필요성\n\n삭제 기한\n\n", "\n\n다음 범주에 속하는 개인정보는 계정 삭제 이후에도 일정 기간 보관될 수 있습니다.\n\n"),
        ("\n\n아동의 개인 정보\n\n수집 목적\n\n업무상 보관 필요성\n\n삭제 기한\n\n", "\n\n연고 관계 증명이 가능한 보호자의 동의를 얻지 못한 경우\n\n"),
        ("\n\n아동의 개인 정보\n\n수집 목적\n\n업무상 보관 필요성\n\n삭제 기한\n\n", "\n\n이용자가 로그인하거나 연고 관계 증명이 가능한 보호자의 동의를 얻기 전에,\n\n"),
        ("\n\n수집 경로\n\n수집하는 영구 식별자\n\n내부 운영 목적\n\n기술적, 조직적 보호 조치\n\n", "\n\n(v) 데이터 공유\n\n"),
        ("\n\n데이터 수신자의 이름 또는 범주\n\n공유되는 개인 정보\n\n공유 목적\n\n법적 근거\n\n", "\n\n(c) 캘리포니아주 거주자 대상 추가 약관\n\n"),
        ("\n\n서버 위치\n\n당사의 서비스 제공에 사용되는 서버의 위치는 다음과 같습니다.\n\n", "\n\nCOGNOSPHERE PTE. LTD.\n\n"),
    ]

    cleaned = section_body
    for start_marker, end_marker in replacements:
        start = cleaned.find(start_marker)
        end = cleaned.find(end_marker, start + len(start_marker)) if start >= 0 else -1
        if start >= 0 and end >= 0:
            cleaned = cleaned[:start] + "\n\n" + cleaned[end:]
    return normalize_text(cleaned)


def split_table_rows(table_body: str) -> tuple[list[str], list[str]]:
    rows = [line.strip() for line in table_body.splitlines() if line.strip().startswith("|")]
    non_rows = [line.strip() for line in table_body.splitlines() if line.strip() and not line.strip().startswith("|")]
    if len(rows) <= 2:
        return non_rows, []
    header = rows[:2]
    data = rows[2:]
    return non_rows + header, data


def build_table_chunks(title: str, tables_text: str) -> list[str]:
    if not tables_text:
        return []
    texts: list[str] = []
    matches = list(TABLE_RE.finditer(tables_text))
    for index, match in enumerate(matches):
        table_number = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tables_text)
        table_block = tables_text[match.end() : end].strip()
        header_lines, data_rows = split_table_rows(table_block)
        meaningful_rows = [row for row in data_rows if row.replace("|", "").strip()]
        if not header_lines and not meaningful_rows:
            continue
        if not meaningful_rows:
            continue
        for start in range(0, len(meaningful_rows), MAX_TABLE_ROWS):
            rows = meaningful_rows[start : start + MAX_TABLE_ROWS]
            row_label = f"row{start + 1}~{start + len(rows)}"
            section_path = f"table-{table_number}-{row_label}"
            table_text = "\n".join([*header_lines, *rows]).strip()
            texts.append(with_prefix(title, section_path, [f"Table {table_number}"], table_text))
    return texts


def rechunk(document: Document) -> list[Chunk]:
    preamble, body, tables = split_document_parts(document.raw_content)
    texts = [*build_main_chunks(document.title, preamble, body), *build_table_chunks(document.title, tables)]
    texts = [text for text in texts if not should_drop_duplicate_section13_table_text(text)]
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


def should_drop_duplicate_section13_table_text(text: str) -> bool:
    if "Section: 13" not in text:
        return False
    duplicate_markers = [
        "아동의 개인 정보\n\n수집 목적",
        "우편번호\n\n거래 및 관련 서비스",
        "Appsflyer SDK",
        "Firebase Analytics SDK",
        "수취인 성명",
        "2026년 2월 25일\n2026년 1월 14일",
    ]
    return any(marker in text for marker in duplicate_markers)


def load_document() -> Document:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT documents_id AS document_id, title, raw_content
                FROM documents
                WHERE documents_id = %s
                """,
                (DOCUMENT_ID,),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"document not found: {DOCUMENT_ID}")
            return Document(**row)


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
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv(".env", override=True)
    document = load_document()
    chunks = rechunk(document)
    print(f"document={document.document_id}")
    print(f"chunks={len(chunks)}")
    print(f"max_chars={max(len(c.chunk_text) for c in chunks)}")
    print(f"min_chars={min(len(c.chunk_text) for c in chunks)}")
    for chunk in chunks[:12]:
        sample = chunk.chunk_text.replace("\n", " ")[:500]
        print(f"- {chunk.chunk_id} order={chunk.chunk_order} chars={len(chunk.chunk_text)} tokens={chunk.token_count}")
        print(f"  {sample}")
    table_count = sum(1 for chunk in chunks if "Section: table-" in chunk.chunk_text)
    print(f"table_chunks={table_count}")
    if args.apply:
        persist_chunks_only(document, chunks)
        print("persisted_chunks_only=true")
    else:
        print("dry_run=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
