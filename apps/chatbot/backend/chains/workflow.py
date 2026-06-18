from __future__ import annotations

from langgraph.graph import END, StateGraph

from chatbot.chains.persistence import draft_persistence_node
from chatbot.chains.routing import route_after_draft_persistence, route_after_preprocess, route_after_safety
from chatbot.generation.bug_agent import bug_agent_node
from chatbot.generation.faq_agent import faq_agent_node
from chatbot.generation.payment_agent import payment_agent_node
from chatbot.generation.response.ticket_completion import ticket_completion_node
from chatbot.generation.ticket_preprocess import ticket_preprocess_node
from chatbot.generation.voc_agent import voc_agent_node
from chatbot.safety.safety_layer import safety_layer_node
from chatbot.schemas import ChatbotState


workflow = StateGraph(ChatbotState)

# 노드 등록: 문의 접수부터 최종 응답 저장까지 챗봇의 전체 처리 단계를 등록한다.
workflow.add_node("ticket_preprocess", ticket_preprocess_node)
workflow.add_node("payment_agent", payment_agent_node)
workflow.add_node("bug_agent", bug_agent_node)
workflow.add_node("faq_agent", faq_agent_node)
workflow.add_node("voc_agent", voc_agent_node)
workflow.add_node("draft_persistence", draft_persistence_node)
workflow.add_node("safety_layer", safety_layer_node)
workflow.add_node("ticket_completion", ticket_completion_node)

# 1단계: 사용자 문의를 전처리하고 qa_ticket에 최초 저장한다.
workflow.set_entry_point("ticket_preprocess")

# 2단계: 전처리 결과와 선택 카테고리에 따라 담당 agent로 분기한다.
# prompt injection처럼 즉시 차단해야 하는 입력은 agent를 거치지 않고 ticket_completion으로 이동한다.
workflow.add_conditional_edges(
    "ticket_preprocess",
    route_after_preprocess,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "voc_agent": "voc_agent",
        "ticket_completion": "ticket_completion",
    },
)

# 3단계: 각 agent가 만든 draft_text를 공통 저장 노드로 보낸다.
for node_name in ("payment_agent", "bug_agent", "faq_agent", "voc_agent"):
    workflow.add_edge(node_name, "draft_persistence")

# 4단계: answer_draft/evidence_docs 저장 후 safety 검사 여부를 결정한다.
# VOC는 고정 응답이라 바로 ticket_completion으로 가고, 나머지는 safety_layer에서 검증한다.
workflow.add_conditional_edges(
    "draft_persistence",
    route_after_draft_persistence,
    {
        "safety_layer": "safety_layer",
        "ticket_completion": "ticket_completion",
    },
)

# 5단계: safety 결과에 따라 재생성, 재저장, fallback/review/block, 최종 응답 경로로 분기한다.
workflow.add_conditional_edges(
    "safety_layer",
    route_after_safety,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "draft_persistence": "draft_persistence",
        "ticket_completion": "ticket_completion",
    },
)

# 6단계: 최종 응답과 티켓 상태를 저장한 뒤 workflow를 종료한다.
workflow.add_edge("ticket_completion", END)

graph = workflow.compile()
