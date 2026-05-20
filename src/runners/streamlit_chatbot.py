from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env", override=True)

import streamlit as st

from chatbot.chains.workflow import graph
from runners.run_chatbot import _last_message_text, build_state


def _reset_chat_state(ticket_start: int = 1000) -> None:
    st.session_state.messages = []
    st.session_state.graph_messages = []
    st.session_state.ticket_counter = ticket_start


def _to_chat_message(message) -> dict | None:
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


st.set_page_config(page_title="CS 챗봇 테스트", layout="centered")
st.title("게임 CS 챗봇 테스트")
st.caption("사용자, 세션, 티켓 흐름을 바꿔가며 테스트합니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "graph_messages" not in st.session_state:
    st.session_state.graph_messages = []
if "ticket_counter" not in st.session_state:
    st.session_state.ticket_counter = 1000
if "user_id" not in st.session_state:
    st.session_state.user_id = "seed-user"
if "session_id" not in st.session_state:
    st.session_state.session_id = "seed-session"

with st.sidebar:
    st.header("설정")
    user_id = st.text_input("user_id", value=st.session_state.user_id)
    session_id = st.text_input("session_id", value=st.session_state.session_id)
    account_id = st.number_input("account_id (0 = 없음)", min_value=0, value=101, step=1)
    ticket_start = st.number_input("ticket_id start", min_value=0, value=1000, step=1)

    st.session_state.user_id = user_id
    st.session_state.session_id = session_id

    st.caption(f"next ticket_id: {st.session_state.ticket_counter + 1}")
    if st.button("새 사용자 대화 시작", use_container_width=True):
        st.session_state.user_id = user_id
        st.session_state.session_id = session_id
        _reset_chat_state(int(ticket_start))
        st.rerun()
    if st.button("전체 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("문의 내용을 입력하세요."):
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    st.session_state.ticket_counter += 1
    ticket_id = st.session_state.ticket_counter
    acc_id = account_id if account_id > 0 else None

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_input,
        account_id=acc_id,
        user_id=st.session_state.user_id,
        session_id=st.session_state.session_id,
        previous_messages=st.session_state.graph_messages,
    )

    result = {}

    print(f"\n{'=' * 60}")
    print(f"[ticket_id={ticket_id}] user_id={st.session_state.user_id} session_id={st.session_state.session_id}")
    print(f"문의: {user_input}")
    print(f"{'=' * 60}")

    with st.chat_message("assistant"):
        with st.spinner("답변 생성 중..."):
            for chunk in graph.stream(state, stream_mode="updates"):
                for node_name, node_update in chunk.items():
                    print(f"\n[{node_name}]")
                    if node_name == "orchestrator":
                        print(f"  category              : {node_update.get('category')}")
                        print(f"  routing_target        : {node_update.get('routing_target')}")
                        print(f"  classification_method : {node_update.get('classification_method')}")
                        print(f"  classification_reason : {node_update.get('classification_reason')}")
                    elif node_name in ("payment_agent", "bug_agent", "faq_agent", "voc_agent"):
                        draft = str(node_update.get("draft_text", ""))
                        print(f"  draft_text            : {draft[:200]}{'...' if len(draft) > 200 else ''}")
                    elif node_name == "safety_layer":
                        print(f"  safety_passed         : {node_update.get('safety_passed')}")
                        print(f"  safety_action         : {node_update.get('safety_action')}")
                        print(f"  retry_count           : {node_update.get('retry_count')}")
                    elif node_name == "final_response":
                        final = str(node_update.get("final_text", ""))
                        print(f"  final_text            : {final[:200]}{'...' if len(final) > 200 else ''}")
                    result.update(node_update)

        answer = _last_message_text(result)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

    raw_messages = result.get("messages", state["messages"])
    st.session_state.graph_messages = [
        message
        for message in (_to_chat_message(item) for item in raw_messages)
        if message is not None
    ]
