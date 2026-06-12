"""분포·변화율 계산 헬퍼 — 보고서 페이로드 조립에 사용."""

from __future__ import annotations

from collections import Counter
from typing import Any


def normalize_text(value: object, *, fallback: str = "unknown") -> str:
    """None, 빈 문자열, 공백만 있는 값을 fallback 문자열로 정규화한다.

    DB에서 NULL이 들어오면 str(None) = "None"이 되므로 None만 빈 문자열로 치환한다. 0 같은 falsy 값은 유효한 값으로 그대로 처리한다.
    """
    text = ("" if value is None else str(value)).strip()
    return text if text else fallback


def distribution(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """rows에서 key 컬럼의 값 분포를 건수 내림차순으로 반환한다.

    반환 형식: [{"label": "결제", "value": 12}, ...]
    동점 항목은 label 오름차순으로 정렬해 매번 같은 순서를 보장한다.
    """
    counts = Counter(normalize_text(row.get(key)) for row in rows)
    return [
        {"label": label, "value": counts[label]}
        for label in sorted(counts, key=lambda item: (-counts[item], item))
    ]


def format_change(current: int | float, previous: int | float) -> str:
    """현재/이전 값을 비교해 변화율 문자열을 반환한다.

    - previous == 0이고 current == 0 → "0" (변동 없음)
    - previous == 0이고 current > 0  → "+{current}" (신규 발생, 퍼센트 계산 불가)
    - 그 외                           → "+12.3%" 또는 "-5.0%" 형식
    """
    if previous == 0:
        if current == 0:
            return "0"
        return f"+{current}"
    return f"{((current - previous) / previous * 100):+.1f}%"
