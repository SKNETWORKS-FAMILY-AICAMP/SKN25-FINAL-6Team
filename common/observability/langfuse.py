"""Shared Langfuse helpers used across applications."""

from __future__ import annotations

import asyncio
import functools
import importlib
import os
from typing import Any, Callable, Final

from dotenv import load_dotenv


_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
_DEFAULT_TRACE_METADATA_FIELDS: Final[tuple[str, ...]] = (
    "ticket_id",
    "session_id",
    "user_id",
    "account_id",
    "ui_category",
    "sub_category",
    "category",
    "routing_target",
    "normalized_query",
    "retrieval_query",
    "retrieval_cache_enabled",
    "retrieval_cache_hit",
    "retrieval_cache_backend",
    "retrieved_count",
    "draft_id",
    "draft_text",
    "analysis_id",
    "admin_id",
    "risk_level",
    "sentiment",
    "safety_action",
    "safety_passed",
    "factuality_score",
    "hallucination_score",
    "review_required",
)

_ACTIVE_CONFIG: dict[str, Any] = {
    "app_name": None,
    "project": None,
    "enabled": False,
    "public_key": "",
    "secret_key": "",
    "host": "",
    "default_tags": [],
    "sdk_available": False,
}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _prefixes_for_app(app_name: str) -> tuple[str, ...]:
    normalized = app_name.strip().replace("-", "_").upper()
    aliases: dict[str, tuple[str, ...]] = {
        "CHATBOT": ("CHATBOT",),
        "CS_AUTO": ("CS_AUTO", "OPERATION"),
        "WEEKLY_REPORT": ("WEEKLY_REPORT", "DASHBOARD"),
    }
    return aliases.get(normalized, (normalized,))


def _langfuse_sdk_available() -> bool:
    try:
        importlib.import_module("langfuse.decorators")
        return True
    except Exception:
        return False


def _set_env_if_present(name: str, value: str) -> None:
    if value:
        os.environ[name] = value


def configure_langfuse(
    app_name: str,
    *,
    default_tags: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Resolve app-specific Langfuse config and expose it process-wide."""

    load_dotenv(override=False)

    prefixes = _prefixes_for_app(app_name)
    enabled = _env_flag("LANGFUSE_ENABLED", False)
    public_key = _non_empty(os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key = _non_empty(os.getenv("LANGFUSE_SECRET_KEY"))
    host = _non_empty(os.getenv("LANGFUSE_HOST"))
    project = _non_empty(os.getenv("LANGFUSE_PROJECT"))

    for prefix in prefixes:
        modern_enabled = os.getenv(f"{prefix}_LANGFUSE_ENABLED")
        if modern_enabled is not None:
            enabled = _env_flag(f"{prefix}_LANGFUSE_ENABLED", enabled)

        modern_public_key = _non_empty(os.getenv(f"{prefix}_LANGFUSE_PUBLIC_KEY"))
        if modern_public_key:
            public_key = modern_public_key

        modern_secret_key = _non_empty(os.getenv(f"{prefix}_LANGFUSE_SECRET_KEY"))
        if modern_secret_key:
            secret_key = modern_secret_key

        modern_host = _non_empty(os.getenv(f"{prefix}_LANGFUSE_HOST"))
        if modern_host:
            host = modern_host

        modern_project = _non_empty(os.getenv(f"{prefix}_LANGFUSE_PROJECT"))
        if modern_project:
            project = modern_project

    sdk_available = _langfuse_sdk_available()
    project = project or app_name
    enabled = bool(enabled and public_key and secret_key and sdk_available)
    tags = list(dict.fromkeys(default_tags or [app_name]))

    _ACTIVE_CONFIG.update(
        {
            "app_name": app_name,
            "project": project,
            "enabled": enabled,
            "public_key": public_key,
            "secret_key": secret_key,
            "host": host,
            "default_tags": tags,
            "sdk_available": sdk_available,
        }
    )

    _set_env_if_present("LANGFUSE_PUBLIC_KEY", public_key)
    _set_env_if_present("LANGFUSE_SECRET_KEY", secret_key)
    _set_env_if_present("LANGFUSE_HOST", host)
    _set_env_if_present("LANGFUSE_PROJECT", project)
    os.environ["LANGFUSE_ENABLED"] = "true" if enabled else "false"

    return dict(_ACTIVE_CONFIG)


def get_langfuse_config() -> dict[str, Any]:
    return dict(_ACTIVE_CONFIG)


def langfuse_enabled() -> bool:
    return bool(_ACTIVE_CONFIG.get("enabled"))


def build_trace_tags(*tags: str | None) -> list[str]:
    merged: list[str] = list(_ACTIVE_CONFIG.get("default_tags") or [])
    for tag in tags:
        if tag and tag.strip():
            merged.append(tag.strip())
    return list(dict.fromkeys(merged))


def build_trace_metadata(
    payload: dict[str, Any],
    *,
    fields: tuple[str, ...] | list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    selected_fields = tuple(fields or _DEFAULT_TRACE_METADATA_FIELDS)
    metadata = {
        field: payload.get(field)
        for field in selected_fields
        if payload.get(field) is not None
    }

    query = payload.get("normalized_query") or payload.get("raw_query")
    if query is not None:
        metadata["normalized_query"] = query

    if "retrieved_count" not in metadata and "retrieved_documents" in payload:
        metadata["retrieved_count"] = len(payload.get("retrieved_documents") or [])

    if _ACTIVE_CONFIG.get("project"):
        metadata.setdefault("langfuse_project", _ACTIVE_CONFIG["project"])
    if _ACTIVE_CONFIG.get("app_name"):
        metadata.setdefault("app_name", _ACTIVE_CONFIG["app_name"])

    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def _langfuse_context() -> Any | None:
    if not langfuse_enabled():
        return None
    try:
        module = importlib.import_module("langfuse.decorators")
        return getattr(module, "langfuse_context", None)
    except Exception:
        return None


def link_current_trace(
    *,
    user_id: str | int | None = None,
    session_id: str | int | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    metadata: dict[str, Any] | None = None,
    input_payload: Any | None = None,
    output_payload: Any | None = None,
) -> None:
    context = _langfuse_context()
    if context is None:
        return

    trace_payload = {
        "user_id": None if user_id is None else str(user_id),
        "session_id": None if session_id is None else str(session_id),
        "tags": build_trace_tags(*(tags or [])),
        "metadata": metadata or {},
    }
    observation_payload = {
        "input": input_payload,
        "output": output_payload,
        "metadata": metadata or {},
    }

    try:
        context.update_current_trace(**trace_payload)
    except Exception:
        pass
    try:
        context.update_current_observation(**observation_payload)
    except Exception:
        pass


def observe_if_enabled(
    *,
    name: str,
    as_type: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a function with Langfuse observe when the SDK is available."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        merged_tags = build_trace_tags(*(tags or []))

        if not langfuse_enabled():
            return func

        try:
            observe = getattr(importlib.import_module("langfuse.decorators"), "observe")
        except Exception:
            return func

        decorator_kwargs: dict[str, Any] = {"name": name}
        if as_type:
            decorator_kwargs["as_type"] = as_type

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def observed_async(*args: Any, **kwargs: Any) -> Any:
                link_current_trace(tags=merged_tags)
                return await func(*args, **kwargs)

            return observe(**decorator_kwargs)(observed_async)

        @functools.wraps(func)
        def observed(*args: Any, **kwargs: Any) -> Any:
            link_current_trace(tags=merged_tags)
            return func(*args, **kwargs)

        return observe(**decorator_kwargs)(observed)

    return decorator
