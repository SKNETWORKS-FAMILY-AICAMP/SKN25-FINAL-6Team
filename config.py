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


settings = Settings()
