"""DB 연결 및 공통 쿼리 헬퍼."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from common.db.connection import db_connection


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


__all__ = ["db_connection", "dict_row", "_fetch_one", "_fetch_all"]
