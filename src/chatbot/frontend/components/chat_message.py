from __future__ import annotations

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
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
