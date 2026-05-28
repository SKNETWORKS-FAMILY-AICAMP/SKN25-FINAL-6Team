"""LangGraph declaration for operation ticket processing."""

from __future__ import annotations

from .nodes import (
    CONTEXT_NODE_BY_ROUTE,
    NODE_FUNCTIONS,
    route_after_retry,
    route_after_save_draft,
    route_by_approval,
    route_by_human_decision,
    route_by_query,
    route_by_target,
)
from .state import OperationState


# save_analysis 이후: rag_reply → RAG 답변 생성 경로, urgent_alert → 긴급 알림 초안 생성 경로
TARGET_ROUTE_TARGETS = {
    "rag_reply": "rag_retrieve_node",
    "urgent_alert": "urgent_draft_node",
}

# save_safety_result_node 이후 3방향 분기
# approved   → 최종 발행, human_review → 운영자 검수 대기, urgent_alert → 즉시 긴급 알림
APPROVAL_ROUTE_TARGETS = {
    "approved": "publish_final_answer_node",
    "human_review": "human_review_node",
    "urgent_alert": "urgent_alert_node",
}

# human_review_node 이후 3방향 분기
# approved → 최종 발행, reject → 재라우팅으로 초안 재생성, edit → 수정 답변 그대로 발행
HUMAN_DECISION_TARGETS = {
    "approved": "publish_final_answer_node",
    "reject": "retry_routing_node",
    "edit": "edit_answer_node",
}

# retry_routing_node 이후 2방향 분기
# retry_count < max_retries → query_router 재진입, 초과 → 긴급 알림으로 에스컬레이션
RETRY_TARGETS = {
    "query_router": "query_router",
    "urgent_alert_node": "urgent_alert_node",
}

# save_draft_node 이후 4방향 분기
# save_evidence_docs  → RAG 근거가 _MIN_EVIDENCE_COUNT 이상일 때 근거 저장 후 승인 게이트
# approval_gate       → (직접 경로, save_evidence_docs 경유 후 진입)
# urgent_alert        → target_route가 urgent_alert인 긴급 알림 경로
# human_review        → RAG 근거 부족( < _MIN_EVIDENCE_COUNT ) 시 사람 검수 직행
SAVE_DRAFT_TARGETS = {
    "save_evidence_docs": "save_evidence_docs_node",
    "approval_gate": "approval_gate_node",
    "urgent_alert": "urgent_alert_node",
    "human_review": "human_review_node",
}

# 조건부 엣지 선언 요약 (참고용 — 실제 등록은 build_operation_graph에서 수행)
CONDITIONAL_EDGES = {
    "query_router": ("route_by_query", CONTEXT_NODE_BY_ROUTE),
    "save_analysis": ("route_by_target", TARGET_ROUTE_TARGETS),
    "save_draft_node": ("route_after_save_draft", SAVE_DRAFT_TARGETS),
    "save_safety_result_node": ("route_by_approval", APPROVAL_ROUTE_TARGETS),
    "human_review_node": ("route_by_human_decision", HUMAN_DECISION_TARGETS),
}

# 고정 엣지 선언 요약 (참고용)
GRAPH_EDGES = (
    ("START", "load_ticket"),
    ("load_ticket", "query_router"),
    ("payment_context_node", "analyze_ticket"),
    ("refund_context_node", "analyze_ticket"),
    ("item_delivery_context_node", "analyze_ticket"),
    ("gacha_context_node", "analyze_ticket"),
    ("policy_context_node", "analyze_ticket"),
    ("abuse_context_node", "analyze_ticket"),
    ("outage_context_node", "analyze_ticket"),
    ("analyze_ticket", "save_analysis"),
    ("rag_retrieve_node", "generate_answer_node"),
    ("generate_answer_node", "save_draft_node"),
    # save_draft_node 이후는 조건부 분기 (SAVE_DRAFT_TARGETS 참고)
    ("save_evidence_docs_node", "approval_gate_node"),
    ("urgent_draft_node", "save_draft_node"),
    ("approval_gate_node", "save_safety_result_node"),
    # retry_routing_node 이후는 조건부 분기 (RETRY_TARGETS 참고)
    ("edit_answer_node", "save_final_edit_node"),
    ("save_final_edit_node", "publish_final_answer_node"),
    ("publish_final_answer_node", "END"),
    ("urgent_alert_node", "END"),
)


def build_operation_graph(*, compile_graph: bool = True):
    """운영 티켓 처리용 LangGraph를 구성합니다.

    `nodes.py`의 DB/LLM 노드와 `state.py`의 `OperationState`를 연결해 실행 가능한 그래프를 만듭니다.

    Args:
        compile_graph: True(기본값)이면 `graph.compile()`을 호출해 실행 가능한 CompiledGraph를 반환한다.
                       False이면 compile 전 StateGraph를 반환한다 (테스트·시각화 용도).
    """

    from langgraph.graph import END, START, StateGraph

    # 노드 등록: NODE_FUNCTIONS의 모든 항목은 _with_node_logging wrapper가 이미 적용되어 있다
    graph = StateGraph(OperationState)
    for node_name, node_handler in NODE_FUNCTIONS.items():
        graph.add_node(node_name, node_handler)

    # 1단계: 티켓 로드 → 문의 유형 분류
    graph.add_edge(START, "load_ticket")
    graph.add_edge("load_ticket", "query_router")

    # 2단계: 유형별 context 노드로 분기 → 모두 analyze_ticket 으로 합류
    graph.add_conditional_edges("query_router", route_by_query, CONTEXT_NODE_BY_ROUTE)
    for context_node in CONTEXT_NODE_BY_ROUTE.values():
        graph.add_edge(context_node, "analyze_ticket")

    # 3단계: 티켓 분석 → DB 저장 → RAG 또는 긴급 알림 분기
    graph.add_edge("analyze_ticket", "save_analysis")
    graph.add_conditional_edges("save_analysis", route_by_target, TARGET_ROUTE_TARGETS)

    # 4단계-A: RAG 답변 경로 — 검색 → 초안 생성 → 저장 → 근거 저장 또는 검수 분기
    graph.add_edge("rag_retrieve_node", "generate_answer_node")
    graph.add_edge("generate_answer_node", "save_draft_node")
    graph.add_conditional_edges(
        "save_draft_node",
        route_after_save_draft,
        SAVE_DRAFT_TARGETS,
    )
    graph.add_edge("save_evidence_docs_node", "approval_gate_node")

    # 4단계-B: 긴급 알림 경로 — 초안 생성 후 save_draft_node 로 합류
    graph.add_edge("urgent_draft_node", "save_draft_node")

    # 5단계: 안전성 검수 → 최종 발행 / 사람 검수 / 긴급 알림 분기
    graph.add_edge("approval_gate_node", "save_safety_result_node")
    graph.add_conditional_edges(
        "save_safety_result_node",
        route_by_approval,
        APPROVAL_ROUTE_TARGETS,
    )

    # 6단계: 사람 검수 → 승인 / 반려(재라우팅) / 편집 분기
    graph.add_conditional_edges(
        "human_review_node",
        route_by_human_decision,
        HUMAN_DECISION_TARGETS,
    )
    # 재시도: 횟수 미초과 → query_router 재진입, 초과 → 긴급 알림 에스컬레이션
    graph.add_conditional_edges("retry_routing_node", route_after_retry, RETRY_TARGETS)

    # 편집 경로: edit_answer_node → save_final_edit_node(상태 확정) → 최종 발행
    # workflow.md §2 및 langgraph.mmd 에 명시된 흐름 (save_final_edit_node 유지)
    graph.add_edge("edit_answer_node", "save_final_edit_node")
    graph.add_edge("save_final_edit_node", "publish_final_answer_node")

    # 종료 노드
    graph.add_edge("publish_final_answer_node", END)
    graph.add_edge("urgent_alert_node", END)

    if compile_graph:
        return graph.compile()
    return graph
