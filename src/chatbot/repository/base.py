from __future__ import annotations

from collections.abc import Callable
from typing import Any

from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import (
    EVENT_DB_READ_COMPLETED,
    EVENT_DB_READ_FAILED,
    EVENT_DB_WRITE_COMPLETED,
    EVENT_DB_WRITE_FAILED,
    log_event,
)


def read_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "ok", "data": rows, "count": len(rows)}


def safe_read(
    *,
    operation: str,
    reader: Callable[[], dict[str, Any]],
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Read failures mean evidence is unavailable, so return an explicit error payload."""
    try:
        result = reader()
        log_event(
            EVENT_DB_READ_COMPLETED,
            ticket_id=ticket_id,
            tool_name=operation,
            status=result.get("status", "ok"),
            metadata={"count": result.get("count")},
        )
        return result
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_DB_READ_FAILED,
            ticket_id=ticket_id,
            tool_name=operation,
            status="error",
            error_message=str(exc),
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "data": [],
            "count": 0,
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": "read failed; evidence unavailable",
        }


def safe_write(
    *,
    operation: str,
    payload: dict[str, Any],
    writer: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Write failures should not block the customer response path."""
    try:
        result = writer()
        log_event(
            EVENT_DB_WRITE_COMPLETED,
            ticket_id=payload.get("ticket_id"),
            tool_name=operation,
            status=result.get("status", "ok"),
            metadata={"stored": result.get("stored"), "result": result},
        )
        return result
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_DB_WRITE_FAILED,
            ticket_id=payload.get("ticket_id"),
            tool_name=operation,
            status="error",
            error_message=str(exc),
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "stored": False,
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": "write failed; customer response can continue",
        }
