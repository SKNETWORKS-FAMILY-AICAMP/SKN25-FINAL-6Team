"""Tabular renderer helpers for dashboard pages."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_data_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("표시할 데이터가 없습니다.")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)

