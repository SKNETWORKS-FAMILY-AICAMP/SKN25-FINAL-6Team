from __future__ import annotations

import streamlit as st

from chatbot.frontend.components.chat_message import to_chat_message
from chatbot.service.chatbot_service import stream_chatbot


def handle_user_message(user_input: str, account_id: int | None) -> None:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    st.session_state.ticket_counter += 1
    ticket_id = st.session_state.ticket_counter

    with st.chat_message("assistant"):
        with st.spinner("문의 내용을 확인하고 있어요..."):
            output = stream_chatbot(
                ticket_id=ticket_id,
                user_message=user_input,
                account_id=account_id,
                user_id=st.session_state.user_id,
                session_id=st.session_state.session_id,
                previous_messages=st.session_state.graph_messages,
            )

        answer = str(output["answer"])
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

    result = output["state"]
    input_state = output["input_state"]
    raw_messages = result.get("messages", input_state["messages"])
    st.session_state.graph_messages = [
        message
        for message in (to_chat_message(item) for item in raw_messages)
        if message is not None
    ]


def render_chat_input(account_id: int | None) -> None:
    if user_input := st.chat_input("문의 내용을 입력하세요."):
        handle_user_message(user_input, account_id)
