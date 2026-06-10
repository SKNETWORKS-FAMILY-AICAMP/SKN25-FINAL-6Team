from __future__ import annotations

from langgraph.graph import END, StateGraph

from chatbot.generation.bug_agent import bug_agent_node
from chatbot.generation.faq_agent import faq_agent_node
from chatbot.generation.payment_agent import payment_agent_node
from chatbot.generation.ticket_preprocess import ticket_preprocess_node
from chatbot.generation.voc_agent import voc_agent_node
from chatbot.chains.persistence import draft_persistence_node
from chatbot.chains.routing import route_after_draft_persistence, route_after_safety, route_by_category
from chatbot.generation.response.final_response import final_response_node
from chatbot.safety.safety_layer import safety_layer_node
from chatbot.schemas import ChatbotState


workflow = StateGraph(ChatbotState)

# 노드 등록: 문의 전처리, 카테고리별 답변 생성, 초안 저장, 안전성 검사, 최종 응답 저장 노드를 등록한다.
workflow.add_node("ticket_preprocess", ticket_preprocess_node)
workflow.add_node("payment_agent", payment_agent_node)
workflow.add_node("bug_agent", bug_agent_node)
workflow.add_node("faq_agent", faq_agent_node)
workflow.add_node("voc_agent", voc_agent_node)
workflow.add_node("draft_persistence", draft_persistence_node)
workflow.add_node("safety_layer", safety_layer_node)
workflow.add_node("final_response", final_response_node)

# 1단계: 사용자 문의를 전처리하고 qa_ticket을 저장한 뒤 category 기반 라우팅 준비를 한다.
workflow.set_entry_point("ticket_preprocess")

# 2단계: 사용자가 선택한 category에 따라 결제/버그/FAQ/VOC agent 노드로 분기한다.
workflow.add_conditional_edges(
    "ticket_preprocess",
    route_by_category,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "voc_agent": "voc_agent",
    },
)

# 3단계: 각 category agent가 draft_text를 만든 뒤 공통 초안 저장 노드로 합류한다.
for node_name in ("payment_agent", "bug_agent", "faq_agent", "voc_agent"):
    workflow.add_edge(node_name, "draft_persistence")

# 4단계: answer_draft와 evidence_docs를 저장한 뒤, VOC는 최종 응답으로 바로 가고 나머지는 safety_layer로 간다.
workflow.add_conditional_edges(
    "draft_persistence",
    route_after_draft_persistence,
    {
        "safety_layer": "safety_layer",
        "final_response": "final_response",
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
        "final_response": "final_response",
    },
)

# 6단계: final_response를 저장하고 qa_ticket 상태를 갱신한 뒤 workflow를 종료한다.
workflow.add_edge("final_response", END)

graph = workflow.compile()
