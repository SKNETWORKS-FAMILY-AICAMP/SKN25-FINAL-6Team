from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from psycopg import connect
from psycopg.rows import tuple_row


BASE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = BASE_DIR.parent
PROJECT_DIR = BUNDLE_DIR.parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
PROCESSED_DATA_DIR = BUNDLE_DIR / "processed_data"
TERM_DOCS_PATH = PROCESSED_DATA_DIR / "hoyoverse_term_policy_notice.csv"
TERM_CHUNKS_PATH = PROCESSED_DATA_DIR / "hoyoverse_term_policy_notice_chunked.csv"
FAQ_CHUNKS_PATH = PROCESSED_DATA_DIR / "hoyoverse_qna_chunked.csv"

DOCUMENT_COLUMNS = [
    "documents_id",
    "source_type",
    "category",
    "title",
    "raw_content",
    "source_url",
    "published_at",
    "updated_at",
]
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536
EMBEDDING_BATCH_SIZE = 100


def load_env() -> None:
    load_dotenv(WORKSPACE_DIR / ".env")
    load_dotenv(PROJECT_DIR / ".env")


def clean_value(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value)
    if text.lower() == "nan":
        return None
    return text


def parse_timestamp(value: object) -> object | None:
    value = clean_value(value)
    if not value:
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.to_pydatetime()


def parent_document_id(chunk_id: str) -> str:
    return re.sub(r"-C\d{3}$", "", str(chunk_id))


def chunk_order(chunk_id: str) -> int:
    match = re.search(r"-C(\d{3})$", str(chunk_id))
    return int(match.group(1)) if match else 1


def token_count(text: object) -> int:
    text = clean_value(text)
    if not text:
        return 0
    return max(1, len(str(text)) // 3)


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [column for column in DOCUMENT_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    return df[DOCUMENT_COLUMNS].copy()


def connect_db():
    load_env()
    return connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
        connect_timeout=10,
        row_factory=tuple_row,
    )


def get_openai_client() -> OpenAI:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY or OPENAI_API_KEY is required to generate embeddings")
    return OpenAI(api_key=api_key)


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sj_documents (
                documents_id VARCHAR PRIMARY KEY,
                source_type VARCHAR,
                category VARCHAR,
                title VARCHAR,
                raw_content TEXT,
                source_url VARCHAR,
                published_at TIMESTAMP,
                updated_at TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sj_documents_chunks (
                chunk_id VARCHAR PRIMARY KEY,
                document_id VARCHAR NOT NULL
                    REFERENCES sj_documents(documents_id)
                    ON DELETE CASCADE,
                chunk_text TEXT NOT NULL,
                chunk_order INTEGER NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS sj_documents_embeddings (
                embedding_id VARCHAR PRIMARY KEY,
                chunk_id VARCHAR NOT NULL UNIQUE
                    REFERENCES sj_documents_chunks(chunk_id)
                    ON DELETE CASCADE,
                embedding_vector vector({EMBEDDING_DIM}) NOT NULL,
                embedding_model VARCHAR NOT NULL,
                source_type VARCHAR,
                category VARCHAR,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sj_documents_chunks_document_id
            ON sj_documents_chunks(document_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sj_documents_embeddings_source_category
            ON sj_documents_embeddings(source_type, category);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sj_documents_embeddings_vector_cosine
            ON sj_documents_embeddings
            USING ivfflat (embedding_vector vector_cosine_ops)
            WITH (lists = 100);
            """
        )
    conn.commit()


def reset_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sj_documents_embeddings;")
        cur.execute("DELETE FROM sj_documents_chunks;")
        cur.execute("DELETE FROM sj_documents;")
    conn.commit()


def insert_documents(conn, documents: pd.DataFrame) -> int:
    rows = [
        (
            clean_value(row.documents_id),
            clean_value(row.source_type),
            clean_value(row.category),
            clean_value(row.title),
            clean_value(row.raw_content),
            clean_value(row.source_url),
            parse_timestamp(row.published_at),
            parse_timestamp(row.updated_at),
        )
        for row in documents.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY sj_documents (
                documents_id,
                source_type,
                category,
                title,
                raw_content,
                source_url,
                published_at,
                updated_at
            ) FROM STDIN
            """
        ) as copy:
            for row in rows:
                copy.write_row(row)
    conn.commit()
    return len(rows)


def upsert_documents(conn, documents: pd.DataFrame) -> int:
    rows = [
        (
            clean_value(row.documents_id),
            clean_value(row.source_type),
            clean_value(row.category),
            clean_value(row.title),
            clean_value(row.raw_content),
            clean_value(row.source_url),
            parse_timestamp(row.published_at),
            parse_timestamp(row.updated_at),
        )
        for row in documents.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sj_documents (
                documents_id,
                source_type,
                category,
                title,
                raw_content,
                source_url,
                published_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (documents_id)
            DO UPDATE SET
                source_type = EXCLUDED.source_type,
                category = EXCLUDED.category,
                title = EXCLUDED.title,
                raw_content = EXCLUDED.raw_content,
                source_url = EXCLUDED.source_url,
                published_at = EXCLUDED.published_at,
                updated_at = EXCLUDED.updated_at;
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def insert_chunks(conn, chunks: pd.DataFrame) -> int:
    rows = []
    for row in chunks.itertuples(index=False):
        chunk_id = clean_value(row.documents_id)
        rows.append(
            (
                chunk_id,
                parent_document_id(str(chunk_id)),
                clean_value(row.raw_content),
                chunk_order(str(chunk_id)),
                token_count(row.raw_content),
            )
        )

    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY sj_documents_chunks (
                chunk_id,
                document_id,
                chunk_text,
                chunk_order,
                token_count
            ) FROM STDIN
            """
        ) as copy:
            for row in rows:
                copy.write_row(row)
    conn.commit()
    return len(rows)


def insert_embeddings(
    conn,
    *,
    client: OpenAI,
    model: str = EMBEDDING_MODEL,
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.chunk_id,
                c.chunk_text,
                d.source_type,
                d.category
            FROM sj_documents_chunks c
            JOIN sj_documents d
              ON d.documents_id = c.document_id
            WHERE c.chunk_text IS NOT NULL
              AND TRIM(c.chunk_text) <> ''
            ORDER BY c.document_id, c.chunk_order;
            """
        )
        chunks = cur.fetchall()

    total_inserted = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        response = client.embeddings.create(
            model=model,
            input=[row[1] for row in batch],
        )

        rows = []
        for row, item in zip(batch, response.data, strict=True):
            chunk_id, _chunk_text, source_type, category = row
            rows.append(
                (
                    f"{chunk_id}::embedding",
                    chunk_id,
                    to_pgvector(item.embedding),
                    model,
                    source_type,
                    category,
                )
            )

        with conn.cursor() as cur:
            with cur.copy(
                """
                COPY sj_documents_embeddings (
                    embedding_id,
                    chunk_id,
                    embedding_vector,
                    embedding_model,
                    source_type,
                    category
                ) FROM STDIN
                """
            ) as copy:
                for row in rows:
                    copy.write_row(row)

        conn.commit()
        total_inserted += len(rows)
        print(f"inserted sj_documents_embeddings: {total_inserted}/{len(chunks)}")

    return total_inserted


def main() -> None:
    with_embeddings = "--with-embeddings" in sys.argv
    documents_only = "--documents-only" in sys.argv

    term_documents = load_csv(TERM_DOCS_PATH)
    term_chunks = load_csv(TERM_CHUNKS_PATH)
    faq_chunks = load_csv(FAQ_CHUNKS_PATH)

    # FAQ는 별도 원본 CSV 없이 chunk 단위로 정리되어 있으므로,
    # chunk id에서 parent document id를 복원해 FK를 만족시킨다.
    faq_parent_documents = faq_chunks.copy()
    faq_parent_documents["documents_id"] = faq_parent_documents["documents_id"].map(parent_document_id)
    documents = pd.concat([term_documents, faq_parent_documents], ignore_index=True)
    documents = documents.drop_duplicates(subset=["documents_id"], keep="first")
    chunks = pd.concat([term_chunks, faq_chunks], ignore_index=True)

    with connect_db() as conn:
        ensure_tables(conn)
        if documents_only:
            document_count = upsert_documents(conn, documents)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM sj_documents;")
                db_document_count = cur.fetchone()[0]

            print(f"upserted sj_documents: {document_count}")
            print(f"db sj_documents count: {db_document_count}")
            print("sj_documents_chunks and sj_documents_embeddings were not modified")
            return

        reset_tables(conn)
        document_count = insert_documents(conn, documents)
        chunk_count = insert_chunks(conn, chunks)
        embedding_count = 0
        if with_embeddings:
            embedding_count = insert_embeddings(conn, client=get_openai_client())

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM sj_documents;")
            db_document_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sj_documents_chunks;")
            db_chunk_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sj_documents_embeddings;")
            db_embedding_count = cur.fetchone()[0]

    print(f"inserted sj_documents: {document_count}")
    print(f"inserted sj_documents_chunks: {chunk_count}")
    print(f"inserted sj_documents_embeddings: {embedding_count}")
    print(f"db sj_documents count: {db_document_count}")
    print(f"db sj_documents_chunks count: {db_chunk_count}")
    print(f"db sj_documents_embeddings count: {db_embedding_count}")


if __name__ == "__main__":
    main()
