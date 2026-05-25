"""Tabular renderer helpers for dashboard pages."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st

from src.dashboard.util.text import localized_rows


TableKind = Literal["default", "inbox", "priority", "safety", "quality", "failure_log", "history", "analysis"]


TABLE_NOTES: dict[TableKind, tuple[str, str]] = {
    "default": ("일반 목록", "지금 보고 있는 데이터를 한눈에 정리했습니다."),
    "inbox": ("문의 목록", "최근에 들어온 문의를 빠르게 훑어볼 수 있게 정리했습니다."),
    "priority": ("우선 확인", "위험도가 높거나 바로 확인이 필요한 항목만 앞에 오도록 보여줍니다."),
    "safety": ("안전 점검", "답변 전 다시 확인해야 할 안전성 관련 항목을 모았습니다."),
    "quality": ("품질 점검", "답변 품질이나 근거 부족 가능성이 있는 항목을 모았습니다."),
    "failure_log": ("실패 기록", "전송이나 처리 중 문제가 난 항목을 중심으로 보여줍니다."),
    "history": ("처리 이력", "시간 순서로 흐름을 따라갈 수 있게 차분한 형태로 보여줍니다."),
    "analysis": ("원본 분석", "세부 값이 많아 원문에 가깝게 확인할 수 있도록 유지했습니다."),
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
    hallucination = _score(row.get("사실과 다른 내용 위험"))
    toxicity = _score(row.get("공격적 표현 위험"))
    policy = _score(row.get("운영 정책 위반 위험"))
    factuality = _score(row.get("사실성 점수"))

    if risk in {"매우 높음", "높음"} or pattern_risk in {"매우 높음", "높음"}:
        return "critical"
    if next_step in {"즉시 확인 필요", "사람 확인 필요"}:
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
        elif "위험" in column and pd.api.types.is_numeric_dtype(formatted[column]):
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
        st.info("보여드릴 내용이 아직 없습니다.")
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
