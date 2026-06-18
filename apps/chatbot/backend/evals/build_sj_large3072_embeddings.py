from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = REPO_ROOT / "packages" / "common-python" / "src"
for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from common.db.connection import db_connection


SOURCE_CHUNKS_TABLE = "test_documents_chunks"
SOURCE_DOCUMENTS_TABLE = "sj_documents"
TARGET_TABLE = "test_documents_embeddings_large_3072"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
EMBEDDING_MODEL_LABEL = f"{EMBEDDING_MODEL}:{EMBEDDING_DIMENSIONS}"


def load_eval_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def embedder() -> Any:
    from langchain_openai import OpenAIEmbeddings

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
        api_key=api_key,
    )


def ensure_table(*, recreate: bool) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            if recreate:
                cur.execute(f"DROP TABLE IF EXISTS {TARGET_TABLE}")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
                    embedding_id varchar PRIMARY KEY,
                    chunk_id varchar NOT NULL,
                    embedding_vector vector({EMBEDDING_DIMENSIONS}),
                    embedding_model varchar,
                    source_type varchar,
                    category varchar,
                    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_{TARGET_TABLE}_chunk_id UNIQUE (chunk_id)
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_chunk_id ON {TARGET_TABLE} (chunk_id)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_source_category ON {TARGET_TABLE} (source_type, category)"
            )
        conn.commit()


def load_pending_chunks(*, limit: int | None) -> list[dict[str, Any]]:
    limit_sql = "LIMIT %s" if limit is not None else ""
    params: tuple[Any, ...] = (limit,) if limit is not None else ()
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    c.chunk_id,
                    c.chunk_text,
                    d.source_type,
                    d.category
                FROM {SOURCE_CHUNKS_TABLE} c
                JOIN {SOURCE_DOCUMENTS_TABLE} d ON d.document_id = c.document_id
                LEFT JOIN {TARGET_TABLE} e ON e.chunk_id = c.chunk_id
                WHERE e.chunk_id IS NULL
                ORDER BY c.document_id, c.chunk_order
                {limit_sql}
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]


def insert_embeddings(rows: list[dict[str, Any]], vectors: list[list[float]]) -> None:
    payload = []
    for row, vector in zip(rows, vectors, strict=True):
        chunk_id = str(row["chunk_id"])
        payload.append(
            (
                f"large3072:{chunk_id}",
                chunk_id,
                vector_literal(vector),
                EMBEDDING_MODEL_LABEL,
                row.get("source_type"),
                row.get("category"),
            )
        )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {TARGET_TABLE} (
                    embedding_id,
                    chunk_id,
                    embedding_vector,
                    embedding_model,
                    source_type,
                    category,
                    created_at
                )
                VALUES (%s, %s, %s::vector, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding_vector = EXCLUDED.embedding_vector,
                    embedding_model = EXCLUDED.embedding_model,
                    source_type = EXCLUDED.source_type,
                    category = EXCLUDED.category,
                    created_at = CURRENT_TIMESTAMP
                """,
                payload,
            )
        conn.commit()


def create_vector_index() -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_vector_cosine
                    ON {TARGET_TABLE}
                    USING ivfflat (embedding_vector vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )
            except Exception as exc:
                if "more than 2000 dimensions" not in str(exc):
                    raise
                conn.rollback()
                print(
                    "Skipped ivfflat index: pgvector vector ivfflat indexes cannot exceed "
                    f"2000 dimensions, but {TARGET_TABLE} stores {EMBEDDING_DIMENSIONS}-dimensional vectors. "
                    "Retrieval will use exact scan unless pgvector is upgraded and a halfvec index path is added."
                )
                return
            cur.execute(f"ANALYZE {TARGET_TABLE}")
        conn.commit()


def count_rows() -> tuple[int, int]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {SOURCE_CHUNKS_TABLE}")
            total = int(cur.fetchone()[0])
            cur.execute(f"SELECT count(*) FROM {TARGET_TABLE}")
            embedded = int(cur.fetchone()[0])
            return total, embedded


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 3072-dimensional SJ test embeddings.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()

    load_eval_env()
    ensure_table(recreate=args.recreate)
    rows = load_pending_chunks(limit=args.limit)
    if not rows:
        total, embedded = count_rows()
        print(f"No pending chunks. {embedded}/{total} rows already embedded in {TARGET_TABLE}.")
        if not args.skip_index:
            create_vector_index()
        return

    client = embedder()
    processed = 0
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        texts = [str(row["chunk_text"]) for row in batch]
        vectors = client.embed_documents(texts)
        insert_embeddings(batch, vectors)
        processed += len(batch)
        total, embedded = count_rows()
        print(f"Embedded batch {processed}/{len(rows)} pending; table={embedded}/{total}")

    if not args.skip_index:
        create_vector_index()
    total, embedded = count_rows()
    print(f"Done. {embedded}/{total} rows embedded in {TARGET_TABLE}.")


if __name__ == "__main__":
    main()
