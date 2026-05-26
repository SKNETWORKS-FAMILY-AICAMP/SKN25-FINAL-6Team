from __future__ import annotations

import streamlit as st


def render_source_box(sources: list[dict] | None = None) -> None:
    if not sources:
        return

    with st.expander("Sources"):
        for index, source in enumerate(sources, start=1):
            title = source.get("title") or source.get("source") or f"Source {index}"
            content = source.get("content") or source.get("text") or ""
            st.markdown(f"**{title}**")
            if content:
                st.caption(str(content))
