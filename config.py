from __future__ import annotations

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# LangChain 등 외부 라이브러리가 os.environ에서 직접 키를 읽으므로 명시적으로 로드한다
# pydantic-settings는 settings 객체에만 값을 담고 os.environ에는 쓰지 않는다
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase PostgreSQL 연결 문자열
    database_url: str = ""
    # OpenAI API 인증 키; langchain_openai 내부에서 자동 참조된다
    openai_api_key: str = ""
    # LLM 식별자; create_agent에 그대로 전달된다 (예: "gpt-4o")
    openai_model: str = ""
    # Chroma ingestion 시 사용한 모델과 반드시 동일해야 한다
    embedding_model: str = ""
    # STEP2 RAG 검색 결과 개수
    retrieval_top_k: int = 3
    # RRF fusion 상수; 값이 클수록 하위 순위 문서의 영향이 줄어든다 (논문 권장값 60)
    rrf_k: int = 60
    # Vector DB 컬렉션명; 실제 Vector DB 연동 시 참조한다
    vector_collection: str = ""
    # Chroma 로컬 파일 경로; 설정 시 in-payload 임베딩 대신 Chroma vector 검색을 사용한다
    chroma_persist_dir: str = ""


settings = Settings()

# run_operation.py가 payload를 embed할 때 사용하는 마커; agent.py가 파싱 기준으로 참조한다
PAYLOAD_MARKER = "First input payload:\n"
