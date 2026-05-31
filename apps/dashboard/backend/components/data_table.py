"""Tabular renderer helpers for dashboard pages."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st

from util.text import localized_rows


TableKind = Literal["default", "inbox", "priority", "safety", "quality", "failure_log", "history", "analysis"]


TABLE_NOTES: dict[TableKind, tuple[str, str]] = {
    "default": ("?쇰컲 紐⑸줉", "?꾩옱 蹂닿퀬 ?덈뒗 ?곗씠?곕? ???뺥깭濡??뺣━?덉뒿?덈떎."),
    "inbox": ("臾몄쓽 紐⑸줉", "理쒓렐???ㅼ뼱??臾몄쓽瑜?鍮좊Ⅴ寃??뺤씤?????덈룄濡??뺣━?덉뒿?덈떎."),
    "priority": ("?곗꽑 ?뺤씤", "?꾪뿕?꾧? ?믨굅??諛붾줈 ?뺤씤???꾩슂????ぉ???욎そ??諛곗튂?덉뒿?덈떎."),
    "safety": ("?덉쟾 ?먭?", "?묐떟 ?꾩뿉 ?ㅼ떆 ?뺤씤?댁빞 ???덉쟾 愿????ぉ?낅땲??"),
    "quality": ("?덉쭏 ?먭?", "?묐떟 ?덉쭏?대굹 洹쇨굅 遺議?媛?μ꽦???덈뒗 ??ぉ?낅땲??"),
    "failure_log": ("?ㅽ뙣 湲곕줉", "?꾩넚?대굹 泥섎━ 以?臾몄젣媛 ?덉뿀????ぉ??紐⑥븯?듬땲??"),
    "history": ("泥섎━ ?대젰", "?쒓컙 ?쒖꽌?濡??먮쫫???곕씪媛湲??쎄쾶 ?뺣━?덉뒿?덈떎."),
    "analysis": ("遺꾩꽍 ?먮낯", "而щ읆??留롮븘 ?곸꽭 ?뺤씤???곹빀???뺥깭濡?蹂댁뿬以띾땲??"),
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _score(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_tone(row: pd.Series, kind: TableKind) -> str:
    risk = _normalize_text(row.get("?꾪뿕??")).lower()
    pattern_risk = _normalize_text(row.get("諛섎났 ?⑦꽩 ?꾪뿕??")).lower()
    status = _normalize_text(row.get("泥섎━ ?곹깭")).lower()
    next_step = _normalize_text(row.get("?ㅼ쓬 泥섎━")).lower()
    failure_type = _normalize_text(row.get("?ㅽ뙣 ?좏삎")).lower()
    hallucination = _score(row.get("?섍컖 ?꾪뿕 ?먯닔"))
    toxicity = _score(row.get("?낆꽦 ?먯닔"))
    policy = _score(row.get("?뺤콉 ?꾨컲 ?먯닔"))
    factuality = _score(row.get("?ъ떎???먯닔"))

    if risk in {"留ㅼ슦 ?믪쓬", "?믪쓬"} or pattern_risk in {"留ㅼ슦 ?믪쓬", "?믪쓬"}:
        return "critical"
    if next_step in {"利됱떆 ?뚮┝", "?щ엺 寃???꾩슂"}:
        return "warning"
    if status in {"?ㅽ뙣", "?ㅻ쪟"} or failure_type in {"?ㅽ뙣", "?ㅻ쪟"}:
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
        if "鍮꾩쑉" in column and pd.api.types.is_numeric_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.1%}" if pd.notna(value) else "-")
        elif "?됯퇏" in column and pd.api.types.is_numeric_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
        elif "?먯닔" in column and pd.api.types.is_numeric_dtype(formatted[column]):
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
            <div style="font-size: 0.82rem; color: #667085; margin-bottom: 4px;">{title} 쨌 {row_count}嫄?/div>
            <div style="font-size: 0.95rem; color: #18202b; line-height: 1.45;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_table(rows: list[dict[str, Any]], *, kind: TableKind = "default") -> None:
    if not rows:
        st.info("?쒖떆???곗씠?곌? ?꾩쭅 ?놁뒿?덈떎.")
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
