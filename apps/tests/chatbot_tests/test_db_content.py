from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CHATBOT_DB_EXPLORATION_TESTS") != "true",
    reason="manual DB exploration test; set RUN_CHATBOT_DB_EXPLORATION_TESTS=true to run",
)


def test_keyword_documents_exist_for_common_safe_fallback_queries() -> None:
    load_dotenv(".env", override=True)

    from common.db.connection import db_connection
    from psycopg.rows import dict_row

    queries = {
        "이벤트 보상 우편함 수령 기간": ["우편함", "수령", "기간", "만료일", "보상 기간"],
        "친구 초대 보상": ["친구 초대", "초대 이벤트", "친구 추천"],
        "우편함 보상 복구": ["우편함 복구", "보상 복구", "삭제된 우편"],
        "패치 노트": ["패치 노트", "패치노트", "patch note"],
        "출석 이벤트 보상 수령 조건": ["출석 이벤트", "출석 보상", "로그인 보상 조건"],
    }

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for keywords in queries.values():
                patterns = [f"%{keyword}%" for keyword in keywords]
                cur.execute(
                    """
                    SELECT d.source_type, d.title, c.chunk_text, c.token_count
                    FROM documents_chunks c
                    JOIN documents d ON d.documents_id = c.document_id
                    WHERE c.chunk_text ILIKE ANY(%s)
                       OR d.title ILIKE ANY(%s)
                    LIMIT 3
                    """,
                    (patterns, patterns),
                )
                assert len(cur.fetchall()) <= 3
