from __future__ import annotations

from collections.abc import Callable
from typing import Any

from observability.error_classifier import classify_error
from observability.logger import (
    EVENT_DB_READ_COMPLETED,
    EVENT_DB_READ_FAILED,
    EVENT_DB_WRITE_COMPLETED,
    EVENT_DB_WRITE_FAILED,
    log_event,
)


# repository read 결과를 공통 응답 형태로 감싼다.
def read_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "ok", "data": rows, "count": len(rows)}


# DB 조회 실패는 답변 근거 부족으로 이어지므로, 예외를 던지지 않고 명시적인 error payload로 반환한다.
def safe_read(
    *,
    operation: str,
    reader: Callable[[], dict[str, Any]],
    ticket_id: int | None = None,
) -> dict[str, Any]:
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
            error_category=error_category,
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


# DB 저장 실패는 고객 응답 생성을 막지 않도록 로그만 남기고 error payload를 반환한다.
def safe_write(
    *,
    operation: str,
    payload: dict[str, Any],
    writer: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
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
            error_category=error_category,
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "stored": False,
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": "write failed; customer response can continue",
        }
