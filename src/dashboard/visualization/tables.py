"""Table helpers for dashboard data views."""

from __future__ import annotations

from typing import Any


def rows_for_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    return [{column: row.get(column) for column in columns} for row in rows]

