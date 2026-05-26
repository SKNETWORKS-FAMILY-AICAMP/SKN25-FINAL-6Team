"""Helpers for mapping service-specific LangSmith env vars to SDK defaults."""

from __future__ import annotations

import os
from typing import Final

from dotenv import load_dotenv


_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def configure_langsmith(service: str) -> dict[str, str | bool]:
    """Apply prefixed env vars for one service to LangSmith's default names."""

    load_dotenv(override=False)

    prefix = service.upper()
    tracing = _env_flag(f"{prefix}_LANGSMITH_TRACING", _env_flag("LANGSMITH_TRACING", False))
    api_key = (
        os.getenv(f"{prefix}_LANGSMITH_API_KEY")
        or os.getenv("LANGSMITH_API_KEY")
        or os.getenv("LANGCHAIN_API_KEY")
        or ""
    ).strip()
    project = (
        os.getenv(f"{prefix}_LANGSMITH_PROJECT")
        or os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or service
    ).strip()

    os.environ["LANGSMITH_TRACING"] = "true" if tracing and bool(api_key) else "false"
    os.environ["LANGCHAIN_TRACING_V2"] = os.environ["LANGSMITH_TRACING"]
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project

    if api_key:
        os.environ["LANGSMITH_API_KEY"] = api_key
        os.environ["LANGCHAIN_API_KEY"] = api_key

    return {
        "service": service,
        "enabled": os.environ["LANGSMITH_TRACING"] == "true",
        "api_key": api_key,
        "project": project,
    }
