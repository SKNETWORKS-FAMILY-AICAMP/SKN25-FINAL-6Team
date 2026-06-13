import sys
sys.path.insert(0, "packages/common-python/src")

from dotenv import load_dotenv
load_dotenv(".env", override=True)

from common.db.connection import db_connection
from psycopg.rows import dict_row

SOURCE_MAP = {
    "faq_document":    ["hoyoverse_qna_common", "hoyoverse_qna_onlygenshin"],
    "notice_document": ["naver_cafe_notice"],
    "policy_document": ["hoyoverse_policy"],
    "game_guide":      ["naver_cafe_guide"],
}

queries = {
    "쿠폰 코드 입력 방법": {
        "keywords": ["쿠폰", "리딤", "코드 입력", "코드 번호"],
        "source_types": SOURCE_MAP["faq_document"] + SOURCE_MAP["notice_document"],
    },
    "이벤트 보상 우편함 수령 기간": {
        "keywords": ["우편", "보상 수령", "이벤트 종료", "우편 유효"],
        "source_types": SOURCE_MAP["notice_document"] + SOURCE_MAP["faq_document"],
    },
    "친구 초대 보상": {
        "keywords": ["친구 초대", "초대 보상", "친구 추천"],
        "source_types": SOURCE_MAP["notice_document"] + SOURCE_MAP["faq_document"],
    },
    "우편함 보상 복구": {
        "keywords": ["복구", "우편 삭제", "보상 재지급", "우편함"],
        "source_types": SOURCE_MAP["policy_document"] + SOURCE_MAP["faq_document"],
    },
    "패치 노트 확인 방법": {
        "keywords": ["업데이트", "패치", "버전 안내", "공지"],
        "source_types": SOURCE_MAP["notice_document"] + SOURCE_MAP["game_guide"],
    },
    "출석 이벤트 보상 수령 조건": {
        "keywords": ["출석", "로그인 보상", "출석 이벤트", "누적 로그인"],
        "source_types": SOURCE_MAP["notice_document"] + SOURCE_MAP["faq_document"],
    },
}

with db_connection() as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        for label, config in queries.items():
            patterns = [f"%{k}%" for k in config["keywords"]]
            source_types = config["source_types"]

            cur.execute("""
                SELECT d.source_type, d.title, c.chunk_text, c.token_count
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                WHERE d.source_type = ANY(%s)
                  AND (c.chunk_text ILIKE ANY(%s) OR d.title ILIKE ANY(%s))
                ORDER BY c.token_count DESC
                LIMIT 3
            """, (source_types, patterns, patterns))
            rows = cur.fetchall()

            print(f"=== {label} ===")
            if not rows:
                print("  ❌ 정답 문서 없음")
            for row in rows:
                print(f"  [{row['source_type']}] {row['title']}")
                print(f"  {row['chunk_text'][:250].replace(chr(10), ' ')}")
                print()
