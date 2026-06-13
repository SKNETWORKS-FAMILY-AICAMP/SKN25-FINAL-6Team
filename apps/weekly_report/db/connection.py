"""DB 쿼리 실행 헬퍼."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from common.db.connection import db_connection


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """단일 행을 조회해 dict로 반환한다. 결과가 없으면 None을 반환한다.

    호출부에서 None 대신 `or {}` 패턴을 쓸 수 있도록 None을 명시적으로 반환한다.
    """
    cur.execute(sql, params)
    row = cur.fetchone()
    # psycopg3 dict_row는 이미 dict-like이지만, 외부에서 dict()로 한번 더 감싸
    # 일반 dict 타입임을 명확히 한다.
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """전체 결과를 dict 리스트로 반환한다. 결과가 없으면 빈 리스트를 반환한다."""
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


# db_connection과 dict_row를 재노출해 각 db/*.py 모듈이 이 파일 하나만 임포트해도 되게 한다.
__all__ = ["db_connection", "dict_row", "_fetch_one", "_fetch_all"]
