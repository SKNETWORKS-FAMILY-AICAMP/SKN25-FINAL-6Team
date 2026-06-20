from __future__ import annotations

import contextvars
import json
import math
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


EVENT_ORCHESTRATION_COMPLETED = "orchestration_completed"
EVENT_AGENT_DRAFTED = "agent_drafted"
EVENT_SAFETY_CHECKED = "safety_checked"
EVENT_FINAL_RESPONSE_CREATED = "final_response_created"
EVENT_NODE_STARTED = "node_started"
EVENT_NODE_COMPLETED = "node_completed"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_DB_READ_COMPLETED = "db_read_completed"
EVENT_DB_READ_FAILED = "db_read_failed"
EVENT_DB_WRITE_COMPLETED = "db_write_completed"
EVENT_DB_WRITE_FAILED = "db_write_failed"
EVENT_NOTIFICATION_DISPATCHED = "notification_dispatched"
EVENT_NOTIFICATION_FAILED = "notification_failed"

_USAGE_TRACKER: contextvars.ContextVar[dict[str, dict[str, Any]] | None] = contextvars.ContextVar(
    "usage_tracker",
    default=None,
)

_MODEL_PRICES_PER_1M = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
}


def build_log_event(event_type: str, **payload: Any) -> dict[str, Any]:
    """Build a structured admin log event without binding to a logging backend yet."""
    return {
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }


def _model_price_key(model: str | None) -> str:
    return str(model or "").split(":", 1)[-1].lower()


def _env_price(model: str | None, direction: str) -> float | None:
    key = re.sub(r"[^A-Za-z0-9]+", "_", _model_price_key(model)).upper().strip("_")
    value = os.environ.get(f"OPENAI_COST_{key}_{direction.upper()}_PER_1M")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _price_per_1m(model: str | None, direction: str) -> float:
    env_value = _env_price(model, direction)
    if env_value is not None:
        return env_value
    prices = _MODEL_PRICES_PER_1M.get(_model_price_key(model), {})
    return float(prices.get(direction, 0.0))


def estimate_tokens(text: str, model: str | None = None) -> int:
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(_model_price_key(model))
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(str(text or "")))
    except Exception:
        return max(1, math.ceil(len(str(text or "")) / 3))


@contextmanager
def usage_tracking_context() -> Iterator[dict[str, dict[str, Any]]]:
    tracker: dict[str, dict[str, Any]] = {}
    token = _USAGE_TRACKER.set(tracker)
    try:
        yield tracker
    finally:
        _USAGE_TRACKER.reset(token)


def record_usage(
    *,
    component: str,
    model: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    successful_requests: int = 1,
    estimated: bool = False,
) -> None:
    tracker = _USAGE_TRACKER.get()
    if tracker is None:
        return

    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    total_tokens = int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens)
    cost_usd = (
        prompt_tokens * _price_per_1m(model, "input")
        + completion_tokens * _price_per_1m(model, "output")
    ) / 1_000_000
    bucket = tracker.setdefault(
        component,
        {
            "component": component,
            "models": {},
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "successful_requests": 0,
            "total_cost_usd": 0.0,
            "estimated": False,
        },
    )
    bucket["models"][_model_price_key(model)] = bucket["models"].get(_model_price_key(model), 0) + 1
    bucket["prompt_tokens"] += prompt_tokens
    bucket["completion_tokens"] += completion_tokens
    bucket["total_tokens"] += total_tokens
    bucket["successful_requests"] += int(successful_requests or 0)
    bucket["total_cost_usd"] += cost_usd
    bucket["estimated"] = bool(bucket["estimated"] or estimated)


def _usage_from_message(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if usage:
        return {
            "prompt_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    return {
        "prompt_tokens": int(token_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(token_usage.get("completion_tokens") or 0),
        "total_tokens": int(token_usage.get("total_tokens") or 0),
    }


def record_chat_model_usage(component: str, model: str | None, message: Any) -> None:
    usage = _usage_from_message(message)
    if not any(usage.values()):
        return
    record_usage(component=component, model=model, **usage, estimated=False)


def record_embedding_usage(component: str, model: str | None, text: str) -> None:
    record_usage(
        component=component,
        model=model,
        prompt_tokens=estimate_tokens(text, model),
        completion_tokens=0,
        successful_requests=1,
        estimated=True,
    )


def summarize_usage(tracker: dict[str, dict[str, Any]]) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    for name, bucket in tracker.items():
        components[name] = {
            **bucket,
            "models": dict(bucket.get("models") or {}),
            "total_cost_usd": round(float(bucket.get("total_cost_usd") or 0.0), 8),
        }
    return {
        "components": components,
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in components.values()),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in components.values()),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in components.values()),
        "successful_requests": sum(int(row.get("successful_requests") or 0) for row in components.values()),
        "total_cost_usd": round(sum(float(row.get("total_cost_usd") or 0.0) for row in components.values()), 8),
        "has_estimated_usage": any(bool(row.get("estimated")) for row in components.values()),
    }


def log_event(
    event_type: str,
    *,
    ticket_id: int | None = None,
    session_id: str | None = None,
    node_name: str | None = None,
    category: str | None = None,
    routing_target: str | None = None,
    classification_method: str | None = None,
    tool_name: str | None = None,
    status: str = "ok",
    error_message: str | None = None,
    error_category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Print and persist a structured admin log event."""
    event = build_log_event(
        event_type,
        ticket_id=ticket_id,
        session_id=session_id,
        node_name=node_name,
        category=category,
        routing_target=routing_target,
        classification_method=classification_method,
        tool_name=tool_name,
        status=status,
        error_message=error_message,
        error_category=error_category,
        metadata=metadata or {},
    )
    print(json.dumps(event, ensure_ascii=False, default=str))
    try:
        from chatbot.repository.admin_log_repository import save_admin_event_log

        save_admin_event_log(event)
    except Exception:
        pass
    return event
