from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from chatbot.frontend.components.chat_input import render_chat_input
from chatbot.frontend.components.chat_message import render_chat_history
from chatbot.frontend.components.login_form import render_login_form
from chatbot.frontend.state.session_state import init_chat_state, reset_chat_state


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="stAppViewContainer"] > .main {
            background: #f8fafc;
        }
        .block-container {
            max-width: 920px;
            padding-top: 3.25rem;
            padding-bottom: 6rem;
        }
        .support-hero {
            margin-bottom: 1.5rem;
            padding-bottom: 1.5rem;
            text-align: center;
        }
        .support-title {
            color: #111827;
            font-size: 2.15rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.25;
            margin: 0;
            text-align: center;
        }
        .support-copy {
            color: #4b5563;
            font-size: 0.98rem;
            margin: 0.5rem 0 0;
            text-align: center;
        }
        div[data-testid="stForm"] {
            border: 1.5px solid #1e3a8a;
            border-radius: 8px;
            padding: 1.25rem 1.35rem 1.35rem;
            background: #ffffff;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
        }
        div[data-testid="stTextInput"] label,
        div[data-testid="stSelectbox"] label {
            color: #1f2937;
            font-weight: 650;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-color: #cbd5e1;
            border-radius: 8px;
            background: #f1f5f9;
        }
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button {
            border: 1px solid #1e3a8a;
            border-radius: 8px;
            background: #1e3a8a;
            color: #ffffff;
            min-height: 3rem;
            font-weight: 700;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            border-color: #172554;
            background: #172554;
            color: #ffffff;
        }
        div[data-testid="stChatMessage"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    st.markdown(
        """
        <section class="support-hero">
            <h1 class="support-title">Chatbot</h1>
            <p class="support-copy">게임 계정으로 로그인한 뒤 문의를 남겨 주세요.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_welcome_message() -> None:
    if st.session_state.messages:
        return
    if not st.session_state.logged_in:
        return
    with st.chat_message("assistant"):
        st.markdown("안녕하세요. 게임 이용 중 불편한 점을 편하게 말씀해 주세요.")


def main() -> None:
    load_dotenv(override=True)

    st.set_page_config(page_title="게임 고객센터", layout="centered")
    _inject_styles()

    init_chat_state()
    account_id = st.session_state.account_id

    _render_header()
    render_login_form()

    if not st.session_state.logged_in:
        return

    _render_welcome_message()
    render_chat_history()
    if st.session_state.messages:
        if st.button("새 문의 시작", use_container_width=False):
            reset_chat_state()
            st.rerun()

    render_chat_input(account_id=account_id)


if __name__ == "__main__":
    main()
