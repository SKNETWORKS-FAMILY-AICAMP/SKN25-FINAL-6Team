"""분포·변화율 계산 헬퍼 — 보고서 페이로드 조립에 사용."""

from __future__ import annotations

from collections import Counter
from typing import Any


def normalize_text(value: object, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def distribution(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(normalize_text(row.get(key)) for row in rows)
    return [
        {"label": label, "value": counts[label]}
        for label in sorted(counts, key=lambda item: (-counts[item], item))
    ]


def format_change(current: int | float, previous: int | float) -> str:
    if previous == 0:
        if current == 0:
            return "0"
        return f"+{current}"
    return f"{((current - previous) / previous * 100):+.1f}%"
