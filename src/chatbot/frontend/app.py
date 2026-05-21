from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from chatbot.frontend.components.chat_input import render_chat_input
from chatbot.frontend.components.chat_message import render_chat_history
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
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 1.5rem;
            padding-bottom: 1.5rem;
        }
        .support-title {
            color: #111827;
            font-size: 2.15rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.25;
            margin: 0;
        }
        div[data-testid="stButton"] > button {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #ffffff;
            color: #1f2937;
            min-height: 3rem;
            font-weight: 650;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: #ef4444;
            color: #dc2626;
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
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_welcome_message() -> None:
    if st.session_state.messages:
        return
    with st.chat_message("assistant"):
        st.markdown(
            "안녕하세요. 게임 이용 중 불편한 점이 있다면 편하게 말씀해 주세요. "
            "확인할 수 있는 내용을 바탕으로 도와드릴게요."
        )


def main() -> None:
    load_dotenv(override=True)

    st.set_page_config(page_title="게임 고객센터", layout="centered")
    _inject_styles()

    init_chat_state()
    account_id = st.session_state.account_id

    _render_header()

    _render_welcome_message()
    render_chat_history()
    if st.session_state.messages:
        if st.button("새 문의 시작", use_container_width=False):
            reset_chat_state()
            st.rerun()

    render_chat_input(account_id=account_id)


if __name__ == "__main__":
    main()
