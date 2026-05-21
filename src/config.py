from __future__ import annotations

import os

from dotenv import load_dotenv

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:
    BaseSettings = None
    SettingsConfigDict = None


# LangChain 등 외부 라이브러리가 os.environ에서 직접 키를 읽으므로 명시적으로 로드한다.
load_dotenv()


if BaseSettings is not None:

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        database_url: str = ""
        llm_api_key: str = ""
        llm_model: str = ""
        embedding_model: str = ""
        retrieval_top_k: int = 3
        rrf_k: int = 60
        vector_collection: str = ""
        chroma_persist_dir: str = ""
        use_seed_payload: bool = True

        @property
        def openai_api_key(self) -> str:
            return self.llm_api_key

        @property
        def openai_model(self) -> str:
            return self.llm_model

else:

    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    class Settings:
        def __init__(self) -> None:
            self.database_url = os.getenv("DATABASE_URL", "")
            self.openai_api_key = os.getenv("LLM_API_KEY", "")
            self.openai_model = os.getenv("LLM_MODEL", "")
            self.embedding_model = os.getenv("EMBEDDING_MODEL", "")
            self.retrieval_top_k = _env_int("RETRIEVAL_TOP_K", 3)
            self.rrf_k = _env_int("RRF_K", 60)
            self.vector_collection = os.getenv("VECTOR_COLLECTION", "")
            self.chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIR", "")
            self.use_seed_payload = _env_bool("USE_SEED_PAYLOAD", True)


settings = Settings()

PAYLOAD_MARKER = "First input payload:\n"
