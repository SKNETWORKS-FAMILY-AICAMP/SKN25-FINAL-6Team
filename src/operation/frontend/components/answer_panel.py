"""Answer draft and review action components for operation Streamlit pages."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st


def render_answer_panel(api_base_url: str, draft: dict[str, Any], reviewer_id: str | None = None) -> None:
    draft_id = draft["draft_id"]
    ticket_id = draft["ticket_id"]
    current_text = draft.get("draft_text") or ""

    st.subheader(f"답변 초안 #{draft_id}")
    edited_text = st.text_area("답변 수정", value=current_text, height=260, key=f"draft_text_{draft_id}")

    cols = st.columns([1, 1, 1])
    if cols[0].button("수정 저장", key=f"edit_{draft_id}", use_container_width=True):
        response = requests.patch(
            f"{api_base_url}/drafts/{draft_id}",
            json={"draft_text": edited_text, "reviewer_id": reviewer_id},
            timeout=15,
        )
        response.raise_for_status()
        st.success("수정본을 저장했습니다.")
        st.rerun()

    if cols[1].button("승인", key=f"approve_{draft_id}", type="primary", use_container_width=True):
        response = requests.post(
            f"{api_base_url}/drafts/{draft_id}/approve",
            json={"final_text": edited_text, "reviewer_id": reviewer_id},
            timeout=15,
        )
        response.raise_for_status()
        st.success(f"문의 #{ticket_id} 답변을 승인했습니다.")
        st.rerun()

    with cols[2].popover("반려"):
        reason = st.text_area("반려 사유", key=f"reject_reason_{draft_id}")
        if st.button("반려 실행", key=f"reject_{draft_id}", use_container_width=True):
            response = requests.post(
                f"{api_base_url}/drafts/{draft_id}/reject",
                json={"reason": reason, "reviewer_id": reviewer_id},
                timeout=15,
            )
            response.raise_for_status()
            st.warning(f"문의 #{ticket_id} 초안을 반려했습니다.")
            st.rerun()
