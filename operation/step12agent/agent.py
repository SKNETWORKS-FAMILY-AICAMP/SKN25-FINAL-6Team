from __future__ import annotations

import json
from typing import Annotated, Optional

# create_agent: LangGraph 기반 ReAct 에이전트를 생성한다.
# ReAct 패턴 — reasoning → tool 선택 → observation → 반복, 결론 도달 시 종료.
# docs: https://docs.langchain.com/oss/python/langchain/agents
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from config import PAYLOAD_MARKER, settings
from operation.step12agent.prompts import STEP1_SYSTEM, STEP2_CONTEXT_TEMPLATE, STEP2_SYSTEM
from operation.step12agent.tools import make_retrieve_evidence_tool, record_ticket_analysis


# ── State ─────────────────────────────────────────────────────────────────────

class Step12State(TypedDict):
    # add_messages: 노드 반환 메시지를 덮어쓰지 않고 기존 리스트에 누적하는 LangGraph reducer
    messages: Annotated[list[BaseMessage], add_messages]
    ticket_analysis: Optional[dict]  # STEP1 → STEP2 전달용 분류 결과
    knowledge_base: Optional[dict]   # payload에서 추출; STEP2 retrieval 클로저에 주입
    evidence_docs: Optional[list]    # STEP2 BM25+vector 검색 결과
    answer_draft: Optional[str]      # STEP2 최종 텍스트 응답


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _extract_payload(content: str) -> dict:
    # PAYLOAD_MARKER(config.py)를 기준으로 payload JSON 위치를 특정한다
    idx = content.find(PAYLOAD_MARKER)
    if idx == -1:
        return {}
    try:
        return json.loads(content[idx + len(PAYLOAD_MARKER):])
    except json.JSONDecodeError:
        return {}


def _find_tool_message(messages: list[BaseMessage], tool_name: str) -> Optional[str]:
    # create_agent는 도구 호출 결과를 ToolMessage.name으로 식별 가능하게 messages에 추가한다
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == tool_name:
            return msg.content
    return None


# ── STEP1 에이전트 ─────────────────────────────────────────────────────────────

# create_agent docs: model은 문자열 식별자("gpt-4o") 또는 초기화된 인스턴스 모두 허용
# system_prompt로 에이전트 역할을 고정하고, tools 리스트로 허용 액션을 제한한다
# knowledge_base가 없는 고정 구성이므로 모듈 로드 시 한 번만 생성한다
_step1_agent = create_agent(
    settings.openai_model,
    tools=[record_ticket_analysis],
    system_prompt=STEP1_SYSTEM,
)


def step1_node(state: Step12State) -> dict:
    first_content = state["messages"][0].content if state["messages"] else ""
    payload = _extract_payload(first_content)

    # invoke docs: {"messages": [...]} 형식이 표준 invocation 방식이다
    result = _step1_agent.invoke({"messages": state["messages"]})

    # .name으로 도구 이름을 참조해 문자열 하드코딩을 제거한다
    raw = _find_tool_message(result["messages"], record_ticket_analysis.name)

    return {
        "messages": result["messages"],
        # raw가 None이면 LLM이 도구를 호출하지 않은 것; _route_after_step1에서 빈 dict로 폴백한다
        "ticket_analysis": json.loads(raw) if raw else None,
        "knowledge_base": payload.get("knowledge_base", {}),
    }


# ── STEP1 → STEP2 라우터 ──────────────────────────────────────────────────────

def _route_after_step1(state: Step12State) -> str:
    # ticket_analysis.routing_target 값에 따라 다음 노드를 결정한다
    # urgent_alert: RAG 검색 없이 긴급 처리 안내 초안만 생성
    # 나머지: STEP2 정상 실행
    ticket_analysis = state.get("ticket_analysis") or {}
    if ticket_analysis.get("routing_target") == "urgent_alert":
        return "urgent"
    return "step2"


def urgent_node(state: Step12State) -> dict:
    # urgent_alert 경로: RAG 없이 운영자 즉시 검토 안내 초안을 반환한다
    ticket_analysis = state.get("ticket_analysis") or {}
    draft = (
        "[긴급 처리 필요]\n"
        f"분류: {ticket_analysis.get('category', '')}\n"
        f"위험도: {ticket_analysis.get('risk_level', '')}\n"
        f"요약: {ticket_analysis.get('summary', '')}\n\n"
        "해당 문의는 HIGH 위험도로 분류되어 자동 답변을 생성하지 않습니다. "
        "운영자가 직접 검토 후 처리하십시오."
    )
    return {
        "answer_draft": draft,
        "evidence_docs": [],
    }


# ── STEP2 에이전트 ─────────────────────────────────────────────────────────────

def step2_node(state: Step12State) -> dict:
    knowledge_base = state.get("knowledge_base") or {}
    ticket_analysis = state.get("ticket_analysis") or {}

    # knowledge_base는 State 런타임 값이므로 노드 호출마다 클로저 도구를 새로 생성해야 한다
    # retrieve_tool을 변수로 저장해 .name 참조 시 동일 인스턴스를 사용한다
    retrieve_tool = make_retrieve_evidence_tool(knowledge_base)

    # tools를 retrieve_tool 하나로만 제한해 STEP2 에이전트의 역할을 단순하게 유지한다
    step2_agent = create_agent(
        settings.openai_model,
        tools=[retrieve_tool],
        system_prompt=STEP2_SYSTEM,
    )

    # STEP2_CONTEXT_TEMPLATE(prompts.py)에 ticket_analysis를 주입해 컨텍스트 메시지를 생성한다
    context_msg = HumanMessage(content=STEP2_CONTEXT_TEMPLATE.format(
        ticket_analysis=json.dumps(ticket_analysis, ensure_ascii=False, indent=2)
    ))

    result = step2_agent.invoke({"messages": list(state["messages"]) + [context_msg]})

    # .name으로 도구 이름을 참조해 문자열 하드코딩을 제거한다
    raw = _find_tool_message(result["messages"], retrieve_tool.name)
    last_ai = next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None)

    return {
        "messages": result["messages"],
        # raw가 None이면 LLM이 retrieve_evidence를 호출하지 않은 것; urgent_node와 동일하게 [] 반환
        "evidence_docs": json.loads(raw) if raw else [],
        "answer_draft": last_ai.content if last_ai else "",
    }


# ── 그래프 ────────────────────────────────────────────────────────────────────

def _build_graph():
    # StateGraph: Step12State를 공유 상태로 삼아 노드 간 데이터를 전달한다
    graph = StateGraph(Step12State)
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_node("urgent", urgent_node)

    graph.add_edge(START, "step1")
    # step1 완료 후 routing_target에 따라 분기한다
    # urgent_alert → urgent 노드 (RAG 생략, 긴급 안내 초안)
    # 그 외 → step2 노드 (정상 RAG 실행)
    graph.add_conditional_edges(
        "step1",
        _route_after_step1,
        {"step2": "step2", "urgent": "urgent"},
    )
    graph.add_edge("step2", END)
    graph.add_edge("urgent", END)
    return graph.compile()


# run_operation.py 및 operation/agent.py에서 import하는 진입점
agent = _build_graph()
