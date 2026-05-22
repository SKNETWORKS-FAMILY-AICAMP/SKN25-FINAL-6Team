from __future__ import annotations

import streamlit as st

from chatbot.frontend.state.session_state import clear_login_state, set_login_state
from chatbot.service.account_service import get_server_regions, login_with_credentials


@st.cache_data(ttl=300)
def _cached_server_regions() -> list[str]:
    return get_server_regions()


def render_login_form() -> None:
    if st.session_state.logged_in:
        st.markdown('<div class="login-status">', unsafe_allow_html=True)
        left, right = st.columns([3, 1])
        with left:
            st.caption(
                f"{st.session_state.email} · "
                f"server={st.session_state.server_region} · "
                f"account_id={st.session_state.account_id} · "
                f"session_id={st.session_state.session_id}"
            )
        with right:
            if st.button("로그아웃", use_container_width=True):
                clear_login_state()
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _, center, _ = st.columns([1, 1.15, 1])
    with center:
        with st.form("game_account_login", clear_on_submit=False):
            email = st.text_input("이메일", placeholder="예: user1@game.com")
            password = st.text_input("비밀번호", type="password")
            server_options = _cached_server_regions()
            server_region = st.selectbox("서버", options=server_options, index=0)
            submitted = st.form_submit_button("로그인", use_container_width=True)

        if submitted:
            login_result = login_with_credentials(email, password, server_region)
            if login_result["login_success"]:
                set_login_state(login_result)
                st.success(login_result["message"])
                st.rerun()
            else:
                st.error(login_result["message"])
