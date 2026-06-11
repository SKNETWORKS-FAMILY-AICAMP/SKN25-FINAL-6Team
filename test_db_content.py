import sys
sys.path.insert(0, "packages/common-python/src")

from dotenv import load_dotenv
load_dotenv(".env", override=True)

from common.db.connection import db_connection
from psycopg.rows import dict_row

queries = {
    "이벤트 보상 우편함 수령 기간": ["우편함", "수령", "기간", "만료일", "보상 기간"],
    "친구 초대 보상":               ["친구 초대", "초대 이벤트", "친구 추천"],
    "우편함 보상 복구":             ["우편함 복구", "보상 복구", "삭제된 우편"],
    "패치 노트":                    ["패치 노트", "패치노트", "patch note"],
    "출석 이벤트 보상 수령 조건":   ["출석 이벤트", "출석 보상", "로그인 보상 조건"],
}

with db_connection() as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        for label, keywords in queries.items():
            patterns = [f"%{k}%" for k in keywords]
            cur.execute("""
                SELECT d.source_type, d.title, c.chunk_text, c.token_count
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                WHERE c.chunk_text ILIKE ANY(%s)
                   OR d.title ILIKE ANY(%s)
                LIMIT 3
            """, (patterns, patterns))
            rows = cur.fetchall()

            print(f"=== {label} ===")
            if not rows:
                print("  ❌ DB에 관련 문서 없음")
            for row in rows:
                print(f"  source: {row['source_type']} | {row['title']}")
                print(f"  내용: {row['chunk_text'][:300].replace(chr(10), ' ')}")
                print()
