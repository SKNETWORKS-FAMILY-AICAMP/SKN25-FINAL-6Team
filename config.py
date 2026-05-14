import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got {value!r}")


@dataclass(frozen=True)
class Settings:
    app_env: str = _get_str("APP_ENV", "local") or "local"
    database_url: str | None = _get_str("DATABASE_URL")
    openai_api_key: str | None = _get_str("OPENAI_API_KEY")
    openai_model: str = _get_str("OPENAI_MODEL", "openai:gpt-5.4") or "openai:gpt-5.4"
    embedding_model: str | None = _get_str("EMBEDDING_MODEL")
    vector_collection: str = _get_str("VECTOR_COLLECTION", "game_cs_docs") or "game_cs_docs"
    log_level: str = _get_str("LOG_LEVEL", "INFO") or "INFO"
    default_timezone: str = _get_str("DEFAULT_TIMEZONE", "Asia/Seoul") or "Asia/Seoul"
    default_ticket_id: int = _get_int("DEFAULT_TICKET_ID", 1001)
    use_seed_payload: bool = _get_bool("USE_SEED_PAYLOAD", True)


settings = Settings()
