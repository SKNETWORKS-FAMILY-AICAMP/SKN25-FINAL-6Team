"""Tabular renderer helpers for dashboard pages."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st

from src.dashboard.util.text import localized_rows


TableKind = Literal["default", "inbox", "priority", "safety", "quality", "failure_log", "history", "analysis"]


TABLE_NOTES: dict[TableKind, tuple[str, str]] = {
    "default": ("일반 목록", "현재 보고 있는 데이터를 표 형태로 정리했습니다."),
    "inbox": ("문의 목록", "최근에 들어온 문의를 빠르게 확인할 수 있도록 정리했습니다."),
    "priority": ("우선 확인", "위험도가 높거나 바로 확인이 필요한 항목을 앞쪽에 배치했습니다."),
    "safety": ("안전 점검", "응답 전에 다시 확인해야 할 안전 관련 항목입니다."),
    "quality": ("품질 점검", "응답 품질이나 근거 부족 가능성이 있는 항목입니다."),
    "failure_log": ("실패 기록", "전송이나 처리 중 문제가 있었던 항목을 모았습니다."),
    "history": ("처리 이력", "시간 순서대로 흐름을 따라가기 쉽게 정리했습니다."),
    "analysis": ("분석 원본", "컬럼이 많아 상세 확인에 적합한 형태로 보여줍니다."),
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _score(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_tone(row: pd.Series, kind: TableKind) -> str:
    risk = _normalize_text(row.get("위험도")).lower()
    pattern_risk = _normalize_text(row.get("반복 패턴 위험도")).lower()
    status = _normalize_text(row.get("처리 상태")).lower()
    next_step = _normalize_text(row.get("다음 처리")).lower()
    failure_type = _normalize_text(row.get("실패 유형")).lower()
    hallucination = _score(row.get("환각 위험 점수"))
    toxicity = _score(row.get("독성 점수"))
    policy = _score(row.get("정책 위반 점수"))
    factuality = _score(row.get("사실성 점수"))

    if risk in {"매우 높음", "높음"} or pattern_risk in {"매우 높음", "높음"}:
        return "critical"
    if next_step in {"즉시 알림", "사람 검토 필요"}:
        return "warning"
    if status in {"실패", "오류"} or failure_type in {"실패", "오류"}:
        return "critical"
    if any(value is not None and value >= 0.7 for value in [hallucination, toxicity, policy]):
        return "critical"
    if factuality is not None and factuality <= 0.3:
        return "warning"
    if kind == "failure_log":
        return "warning"
    return "normal"


def _row_style(row: pd.Series, kind: TableKind) -> list[str]:
    tone = _row_tone(row, kind)
    if tone == "critical":
        style = "background-color: #fff1f2; border-left: 4px solid #e11d48;"
    elif tone == "warning":
        style = "background-color: #fff7ed; border-left: 4px solid #f97316;"
    elif kind in {"history", "analysis"}:
        style = "background-color: #f8fafc;"
    elif kind == "inbox":
        style = "background-color: #f8fbff;"
    else:
        style = "background-color: #ffffff;"
    return [style] * len(row)


def _format_frame(frame: pd.DataFrame) -> pd.DataFrame:
    formatted = frame.copy()
    for column in formatted.columns:
        if "비율" in column and pd.api.types.is_numeric_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.1%}" if pd.notna(value) else "-")
        elif "평균" in column and pd.api.types.is_numeric_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
        elif "점수" in column and pd.api.types.is_numeric_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
    return formatted


def _render_table_header(kind: TableKind, row_count: int) -> None:
    title, description = TABLE_NOTES[kind]
    st.markdown(
        f"""
        <div style="
            padding: 12px 14px;
            margin-bottom: 8px;
            border: 1px solid #d7dde5;
            border-radius: 10px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        ">
            <div style="font-size: 0.82rem; color: #667085; margin-bottom: 4px;">{title} · {row_count}건</div>
            <div style="font-size: 0.95rem; color: #18202b; line-height: 1.45;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_table(rows: list[dict[str, Any]], *, kind: TableKind = "default") -> None:
    if not rows:
        st.info("표시할 데이터가 아직 없습니다.")
        return

    localized = localized_rows(rows)
    frame = pd.DataFrame(localized)
    display = _format_frame(frame)
    styled = display.style.apply(lambda row: _row_style(row, kind), axis=1)
    styled = styled.set_properties(**{"font-size": "0.92rem", "white-space": "normal"})

    _render_table_header(kind, len(rows))
    height = min(520, max(180, 56 + (len(display) * 36)))
    if kind in {"history", "analysis"}:
        height = min(620, max(220, 56 + (len(display) * 34)))
    st.dataframe(styled, use_container_width=True, hide_index=True, height=height)
