from __future__ import annotations

from chatbot.agent import invoke_bug_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import BUG_POLICY
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.schemas import ChatbotState


def bug_agent_node(state: ChatbotState) -> dict:
    # 1단계: 버그 문의는 자동 확정 답변보다 재현 정보 수집/검토 안내 중심으로 초안을 만든다.
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    result = invoke_bug_agent(state)
    update = build_draft_update(state, result, BUG_POLICY.name)

    # 2단계: 생성된 버그 초안 길이를 기록하고 공통 draft_persistence 노드로 넘긴다.
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_length": len(update.get("draft_text") or "")},
    )
    return update
