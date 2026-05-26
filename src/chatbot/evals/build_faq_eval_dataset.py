from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from common.db.connection import db_connection


FAQ_SOURCE_TYPES = (
    "hoyoverse_qna_onlygenshin",
    "hoyoverse_qna_common",
    "hoyoverse_policy",
    "naver_cafe_guide",
    "naver_cafe_notice",
)


def _compact(text: str, *, max_chars: int) -> str:
    return " ".join((text or "").split())[:max_chars]


def _question_from_title(title: str, category: str | None) -> str:
    title = _compact(title, max_chars=120).rstrip(".?! ")
    if not title:
        title = _compact(category or "서비스 이용", max_chars=40)
    if title.endswith("?"):
        return title
    return f"{title}에 대해 알려주세요."


def _make_reference(title: str, chunk_text: str, raw_content: str | None) -> str:
    source = chunk_text or raw_content or title
    reference = _compact(source, max_chars=700)
    if title and title not in reference[:120]:
        return f"{_compact(title, max_chars=120)}: {reference}"
    return reference


def _reference_retrieval_trace(question: str) -> list[dict[str, Any]]:
    return [
        {"step": "refine_query_text", "input": question},
        {"step": "embed_query"},
        {"step": "search_document_chunks", "prefer_faq": True},
        {"step": "rerank_documents"},
    ]


def _build_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen_questions: set[str] = set()
    for record in records:
        title = record.get("title") or ""
        category = record.get("category")
        question = _question_from_title(title, category)
        if question in seen_questions:
            question = f"{question.rstrip('?')} ({record['chunk_id']})?"
        seen_questions.add(question)

        rows.append(
            {
                "user_input": question,
                "response": "",
                "reference": _make_reference(title, record.get("chunk_text") or "", record.get("raw_content")),
                "agent_reference": "FAQ/RAG 문서를 검색하고 검색된 근거에 충실한 고객 응답을 생성한다.",
                "reference_topics": ["game_cs", "faq", "policy"],
                "reference_retrieval_trace": _reference_retrieval_trace(question),
                "actual_tool_calls": [],
                "retrieval_trace": [],
                "source_document_id": record["documents_id"],
                "source_chunk_id": record["chunk_id"],
                "source_type": record.get("source_type"),
                "category": category,
                "title": title,
            }
        )
    return rows


def load_faq_records(limit: int, *, min_chars: int) -> list[dict[str, Any]]:
    placeholders = ", ".join(["%s"] * len(FAQ_SOURCE_TYPES))
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT DISTINCT ON (d.documents_id)
                    d.documents_id,
                    d.source_type,
                    d.category,
                    d.title,
                    d.raw_content,
                    c.chunk_id,
                    c.chunk_text,
                    c.chunk_order
                FROM documents d
                JOIN documents_chunks c ON c.document_id = d.documents_id
                WHERE
                    length(c.chunk_text) >= %s
                    AND d.source_type IN ({placeholders})
                ORDER BY d.documents_id, c.chunk_order ASC
                LIMIT %s
                """,
                (min_chars, *FAQ_SOURCE_TYPES, limit),
            )
            return [dict(row) for row in cur.fetchall()]


def save_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a draft FAQ/RAG evaluation dataset from DB documents.")
    parser.add_argument("--output", default="src/chatbot/evals/datasets/faq_ragas_db_seed.jsonl")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-chars", type=int, default=80)
    args = parser.parse_args()

    load_dotenv(override=True)
    records = load_faq_records(args.limit, min_chars=args.min_chars)
    rows = _build_rows(records)
    save_jsonl(Path(args.output), rows)
    print(f"Saved {len(rows)} DB-based FAQ eval seed rows to {args.output}")


if __name__ == "__main__":
    main()
