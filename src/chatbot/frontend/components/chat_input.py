from __future__ import annotations

import re

import streamlit as st

from chatbot.frontend.components.chat_message import to_chat_message
from chatbot.service.chatbot_service import stream_chatbot


def _is_rate_limit_error(exc: Exception) -> bool:
    error_text = str(exc).lower()
    return "ratelimiterror" in type(exc).__name__.lower() or "rate limit" in error_text or "429" in error_text


def _retry_after_seconds(exc: Exception) -> str | None:
    match = re.search(r"try again in ([0-9.]+)s", str(exc), flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _friendly_error_message(exc: Exception) -> str:
    if _is_rate_limit_error(exc):
        retry_after = _retry_after_seconds(exc)
        if retry_after:
            return f"지금 요청이 잠시 몰려 답변을 만들지 못했어요. 약 {retry_after}초 뒤에 다시 시도해 주세요."
        return "지금 요청이 잠시 몰려 답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
    return "답변을 만드는 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요."


def handle_user_message(user_input: str, account_id: int | None) -> None:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    st.session_state.ticket_counter += 1
    ticket_id = st.session_state.ticket_counter

    with st.chat_message("assistant"):
        with st.spinner("문의 내용을 확인하고 있어요..."):
            try:
                output = stream_chatbot(
                    ticket_id=ticket_id,
                    user_message=user_input,
                    account_id=account_id,
                    user_id=st.session_state.user_id,
                    session_id=st.session_state.session_id,
                    previous_messages=st.session_state.graph_messages,
                )
            except Exception as exc:
                print(f"[chatbot_frontend_error] {type(exc).__name__}: {exc}")
                answer = _friendly_error_message(exc)
                st.warning(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                return

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
