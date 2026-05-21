"""Visualization helpers for the dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd


def as_table_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    return [{column: row.get(column) for column in columns} for row in rows]


def as_bar_chart(rows: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    if "label" not in frame.columns or "value" not in frame.columns:
        return frame
    return frame.set_index("label")[["value"]]


def as_line_chart(rows: list[dict[str, Any]], *, x_key: str, y_key: str) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    if x_key not in frame.columns or y_key not in frame.columns:
        return frame
    frame = frame[[x_key, y_key]].dropna()
    if frame.empty:
        return None
    frame[x_key] = pd.to_datetime(frame[x_key], errors="coerce")
    frame = frame.dropna(subset=[x_key])
    if frame.empty:
        return None
    grouped = frame.groupby(frame[x_key].dt.date)[y_key].count().reset_index(name="count")
    grouped = grouped.rename(columns={x_key: "date"}).set_index("date")
    return grouped
