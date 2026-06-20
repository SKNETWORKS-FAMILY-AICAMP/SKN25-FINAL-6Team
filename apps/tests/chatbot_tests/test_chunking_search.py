from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CHATBOT_DB_EXPLORATION_TESTS") != "true",
    reason="manual DB exploration test; set RUN_CHATBOT_DB_EXPLORATION_TESTS=true to run",
)


def test_chunking_vector_search_examples() -> None:
    load_dotenv(".env", override=True)

    from common.db.connection import db_connection
    from langchain_openai import OpenAIEmbeddings
    from psycopg.rows import dict_row

    questions = [
        "쿠폰 코드는 어디에서 입력하나요?",
        "이벤트 보상은 우편함에서 언제까지 받을 수 있나요?",
        "친구 초대 보상은 어떻게 받나요?",
        "우편함 보상이 삭제되면 복구할 수 있나요?",
        "패치 노트는 어디에서 볼 수 있나요?",
        "출석 이벤트 보상 수령 조건은 무엇인가요?",
    ]
    model_name = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    if model_name.startswith("openai:"):
        model_name = model_name.split(":", 1)[1]

    embedder = OpenAIEmbeddings(model=model_name, api_key=os.environ.get("LLM_API_KEY"))

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for question in questions:
                vector = embedder.embed_query(question)
                vector_literal = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"
                cur.execute(
                    f"""
                    SELECT
                        c.chunk_id,
                        c.chunk_text,
                        1 - (e.embedding_vector <=> '{vector_literal}'::vector) AS cosine_score
                    FROM test_documents_chunks c
                    JOIN test_documents_embeddings e ON e.chunk_id = c.chunk_id
                    ORDER BY e.embedding_vector <=> '{vector_literal}'::vector
                    LIMIT 3
                    """
                )
                assert len(cur.fetchall()) <= 3
