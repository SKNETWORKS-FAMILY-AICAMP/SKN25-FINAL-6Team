from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

loaded_chatbot = sys.modules.get("chatbot")
loaded_chatbot_file = getattr(loaded_chatbot, "__file__", "") if loaded_chatbot else ""
if loaded_chatbot_file and not str(loaded_chatbot_file).startswith(str(SRC_ROOT)):
    for module_name in list(sys.modules):
        if module_name == "chatbot" or module_name.startswith("chatbot."):
            del sys.modules[module_name]

from dotenv import load_dotenv
import streamlit as st

from chatbot.frontend.components.chat_input import render_chat_input, resolve_pending_message
from chatbot.frontend.components.chat_message import render_chat_history
from chatbot.frontend.components.login_form import render_login_form, render_login_status
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
            max-width: 1120px;
            padding-top: 1.6rem;
            padding-bottom: 4.5rem;
        }
        .st-key-chat_frame {
            min-height: 78vh;
            border: 1px solid #edf6fd;
            border-radius: 14px;
            background: #f6fbff;
            padding: 2.8rem 2.5rem 1.2rem;
            box-shadow: 0 18px 46px rgba(15, 23, 42, 0.05);
        }
        .st-key-chat_frame .support-hero {
            margin-top: 0.5rem;
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
        .logout-row {
            margin-top: -0.9rem;
            margin-bottom: 0.35rem;
        }
        .logout-row div[data-testid="stButton"] > button {
            min-height: 2.25rem;
            border-radius: 999px;
            font-size: 0.84rem;
            padding: 0.25rem 0.8rem;
        }
        .login-status {
            margin-top: 1rem;
            text-align: center;
        }
        .login-status [data-testid="stCaptionContainer"] {
            color: #6b7280;
        }
        .new-chat-row {
            margin: 0.45rem 0 0.6rem;
        }
        .new-chat-row div[data-testid="stButton"] > button {
            width: auto;
            min-height: 2rem;
            border: 1px solid #dbe3ef;
            border-radius: 999px;
            background: #ffffff;
            color: #64748b;
            font-size: 0.86rem;
            font-weight: 650;
            padding: 0.2rem 0.75rem;
        }
        .new-chat-row div[data-testid="stButton"] > button:hover {
            border-color: #b7e4fb;
            background: #f0f9ff;
            color: #0f172a;
        }
        .chat-row {
            display: flex;
            align-items: flex-start;
            gap: 0.7rem;
            margin: 0.75rem 0;
            width: 100%;
        }
        .chat-row-user {
            flex-direction: row-reverse;
            justify-content: flex-start;
        }
        .chat-row-assistant {
            justify-content: flex-start;
        }
        .chat-avatar {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 2.25rem;
            height: 2.25rem;
            flex: 0 0 2.25rem;
            border-radius: 8px;
            background: #f2a737;
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 800;
            line-height: 1;
        }
        .chat-row-user .chat-avatar {
            background: #ef5b58;
        }
        .chat-bubble {
            max-width: min(74%, 720px);
            padding: 0.85rem 1rem;
            border-radius: 8px;
            color: #1f2937;
            font-size: 0.98rem;
            line-height: 1.6;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: keep-all;
        }
        .chat-bubble-user {
            background: #eef2f7;
            text-align: left;
        }
        .chat-bubble-assistant {
            background: #ffffff;
            border: 1px solid #e5edf6;
            text-align: left;
        }
        [data-testid="stChatInputSubmitButton"] {
            background: #7dd3fc !important;
            color: #0f172a !important;
        }
        [data-testid="stChatInputSubmitButton"]:hover {
            background: #38bdf8 !important;
            color: #0f172a !important;
        }
        [data-testid="stChatInput"] {
            margin-top: 4.2rem;
        }
        [data-testid="stChatInput"] > div {
            min-height: 4.1rem;
            border-radius: 12px;
        }
        [data-testid="stChatInput"] textarea {
            min-height: 3.15rem !important;
            padding-top: 0.95rem !important;
            padding-bottom: 0.95rem !important;
            font-size: 1rem !important;
        }
        @media (max-width: 640px) {
            .chat-bubble {
                max-width: calc(100% - 3rem);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    support_copy = ""
    if not st.session_state.logged_in:
        support_copy = '<p class="support-copy">게임 계정으로 로그인한 뒤 문의를 남겨 주세요.</p>'

    st.markdown(
        f"""
        <section class="support-hero">
            <h1 class="support-title">Chatbot</h1>
            {support_copy}
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

    if st.session_state.logged_in:
        render_login_form()

    if not st.session_state.logged_in:
        _render_header()
        render_login_form()

    if not st.session_state.logged_in:
        return

    with st.container(border=False, key="chat_frame"):
        _render_header()
        _render_welcome_message()
        render_chat_history()
        resolve_pending_message(account_id=account_id)
        if st.session_state.messages:
            st.markdown('<div class="new-chat-row">', unsafe_allow_html=True)
            if st.button("새 채팅", use_container_width=False):
                reset_chat_state()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        render_chat_input(account_id=account_id)
        render_login_status()


if __name__ == "__main__":
    main()
