"""Chart wrapper helpers for dashboard pages."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render_chart_box(title: str, data: Any, *, kind: str = "bar") -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if data is None:
            st.info("표시할 데이터가 없습니다.")
            return
        if isinstance(data, pd.DataFrame):
            if kind == "line":
                st.line_chart(data)
            else:
                st.bar_chart(data)
            return
        st.write(data)
