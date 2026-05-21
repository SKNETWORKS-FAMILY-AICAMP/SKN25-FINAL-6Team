"""Simple metric card renderer for the dashboard."""

from __future__ import annotations

import streamlit as st


def render_metric_card(label: str, value: str | int | float, caption: str | None = None) -> None:
    with st.container(border=True):
        st.metric(label, value, caption=caption)

