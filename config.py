from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default



@dataclass(frozen=True)
class Settings:
    database_url: str = _get_str("DATABASE_URL")
    openai_api_key: str = _get_str("OPENAI_API_KEY")
    openai_model: str = _get_str("OPENAI_MODEL")
    embedding_model: str = _get_str("EMBEDDING_MODEL")
    retrieval_top_k: int = _get_int("RETRIEVAL_TOP_K", 3)
    # RRF fusion 상수; 값이 클수록 하위 순위 문서의 영향이 줄어든다 (논문 권장값 60)
    rrf_k: int = _get_int("RRF_K", 60)
    # Vector DB 컬렉션명; 실제 Vector DB 연동 시 참조한다
    vector_collection: str = _get_str("VECTOR_COLLECTION")
    # Chroma 로컬 파일 경로; 설정 시 in-payload 임베딩 대신 Chroma vector 검색을 사용한다
    chroma_persist_dir: str = _get_str("CHROMA_PERSIST_DIR")


settings = Settings()

# run_operation.py가 payload를 embed할 때 사용하는 마커; agent.py가 파싱 기준으로 참조한다
PAYLOAD_MARKER = "First input payload:\n"
