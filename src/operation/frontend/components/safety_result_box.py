"""Safety review rendering helpers for operation Streamlit pages."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_safety_result_box(safety_result: dict[str, Any] | None) -> None:
    if not safety_result:
        st.info("안전성 검수 결과가 없습니다.")
        return

    with st.container(border=True):
        st.markdown("**안전성 검수**")
        cols = st.columns(4)
        cols[0].metric("환각", safety_result.get("hallucination_score", "-"))
        cols[1].metric("위험 표현", safety_result.get("toxicity_score", "-"))
        cols[2].metric("정책 위반", safety_result.get("policy_violation_score", "-"))
        cols[3].metric("근거 일치", safety_result.get("factuality_score", "-"))
        st.caption(f"조치: {safety_result.get('safety_action') or '-'}")
        if safety_result.get("safety_reason"):
            st.write(safety_result["safety_reason"])
