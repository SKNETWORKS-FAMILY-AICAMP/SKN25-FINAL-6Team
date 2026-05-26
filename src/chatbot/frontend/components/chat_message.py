from __future__ import annotations

from html import escape

import streamlit as st


def to_chat_message(message) -> dict | None:
    if isinstance(message, dict):
        role = message.get("role") or message.get("type")
        content = message.get("content", "")
    else:
        role = getattr(message, "type", None) or getattr(message, "role", "assistant")
        content = getattr(message, "content", str(message))

    if role in ("tool", "function"):
        return None
    if role == "human":
        role = "user"
    if role == "ai":
        role = "assistant"
    if role not in ("user", "assistant", "system"):
        return None
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    return {"role": role, "content": str(content)}


def render_chat_history() -> None:
    for message in st.session_state.messages:
        role = message["role"]
        content = escape(str(message["content"]))
        if role == "user":
            label = "나"
            row_class = "chat-row-user"
            bubble_class = "chat-bubble-user"
        else:
            label = "AI"
            row_class = "chat-row-assistant"
            bubble_class = "chat-bubble-assistant"

        st.markdown(
            f"""
            <div class="chat-row {row_class}">
                <div class="chat-avatar">{label}</div>
                <div class="chat-bubble {bubble_class}">{content}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
