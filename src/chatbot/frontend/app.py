from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from chatbot.frontend.components.chat_input import render_chat_input
from chatbot.frontend.components.chat_message import render_chat_history
from chatbot.frontend.state.session_state import init_chat_state, reset_chat_state


def main() -> None:
    load_dotenv(override=True)

    st.set_page_config(page_title="Game CS Chatbot", layout="centered")
    st.title("Game CS Chatbot")
    st.caption("Streamlit test UI for the chatbot workflow.")

    init_chat_state()

    with st.sidebar:
        st.header("Settings")
        user_id = st.text_input("user_id", value=st.session_state.user_id)
        session_id = st.text_input("session_id", value=st.session_state.session_id)
        account_id = st.number_input("account_id (0 = none)", min_value=0, value=101, step=1)
        ticket_start = st.number_input("ticket_id start", min_value=0, value=1000, step=1)

        st.session_state.user_id = user_id
        st.session_state.session_id = session_id

        st.caption(f"next ticket_id: {st.session_state.ticket_counter + 1}")
        if st.button("Reset conversation", use_container_width=True):
            st.session_state.user_id = user_id
            st.session_state.session_id = session_id
            reset_chat_state(int(ticket_start))
            st.rerun()
        if st.button("Clear all", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    render_chat_history()
    render_chat_input(account_id=account_id)


if __name__ == "__main__":
    main()
