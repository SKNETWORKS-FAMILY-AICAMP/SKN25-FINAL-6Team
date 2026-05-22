from __future__ import annotations

import os
from typing import Any

from chatbot.observability.logger import EVENT_NODE_COMPLETED, log_event
from chatbot.observability.langsmith import build_runnable_config, build_trace_metadata


def build_state(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    messages = list(previous_messages or [])
    messages.append({
        "role": "user",
        "content": (
            f"ticket_id={ticket_id}\n"
            f"account_id={account_id}\n"
            f"source_type={source_type}\n\n"
            f"Customer inquiry:\n{user_message}"
        ),
    })

    return {
        "messages": messages,
        "user_id": user_id,
        "session_id": session_id,
        "account_id": account_id,
        "source_type": source_type,
        "raw_query": user_message,
        "enriched_query": None,
        "ticket_id": ticket_id,
        "category": "",
        "routing_target": "",
        "classification_method": None,
        "classification_reason": None,
        "analysis_id": None,
        "draft_id": None,
        "draft_text": None,
        "final_text": None,
        "reasoning_node": None,
        "safety_passed": None,
        "safety_action": None,
        "safety_reason": None,
        "review_required": None,
        "retry_count": 0,
        "conversation_summary": None,
        "turn_count": len([message for message in messages if message.get("role") == "user"]),
    }


def last_message_text(result: dict[str, Any]) -> str:
    if result.get("final_text"):
        return str(result["final_text"])
    if result.get("draft_text"):
        return str(result["draft_text"])

    messages = result.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    content = (
        last_message.get("content", "")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _node_summary(node_name: str, node_update: dict[str, Any], state_snapshot: dict[str, Any]) -> dict[str, Any]:
    merged = {**state_snapshot, **node_update}
    title_by_node = {
        "orchestrator": "문의 분류",
        "payment_agent": "결제 확인",
        "bug_agent": "버그 확인",
        "faq_agent": "FAQ/RAG 검색",
        "voc_agent": "VOC 처리",
        "draft_persistence": "답변 초안 저장",
        "safety_layer": "안전성 검사",
        "final_response": "최종 응답",
    }
    title = title_by_node.get(node_name, node_name)

    if node_name == "orchestrator":
        detail = (
            f"{merged.get('category') or '미분류'} / {merged.get('routing_target') or '미정'}로 분류했습니다."
            f" 방식: {merged.get('classification_method') or 'unknown'}"
        )
    elif node_name == "faq_agent":
        docs = merged.get("retrieved_documents") or []
        failure = merged.get("faq_failure_reason")
        query = merged.get("retrieval_query") or merged.get("enriched_query") or merged.get("raw_query")
        if failure:
            detail = f"검색어 '{query}'로 문서를 찾았지만 자동 답변 근거가 부족했습니다. 사유: {failure}"
        else:
            detail = f"검색어 '{query}'로 문서 {len(docs)}개를 검색해 답변 초안을 만들었습니다."
    elif node_name == "payment_agent":
        detail = "결제/계정 확인이 필요한 문의로 판단해 운영 확인용 답변 초안을 만들었습니다."
    elif node_name == "bug_agent":
        detail = "버그/게임 상태 확인이 필요한 문의로 판단해 답변 초안을 만들었습니다."
    elif node_name == "voc_agent":
        detail = "의견/건의성 문의로 접수 안내 응답을 준비했습니다."
    elif node_name == "draft_persistence":
        detail = (
            f"초안 draft_id={merged.get('draft_id')}를 저장하고 "
            f"근거 {merged.get('evidence_count', 0)}개를 연결했습니다."
        )
    elif node_name == "safety_layer":
        detail = (
            f"{merged.get('safety_action') or 'UNKNOWN'} 결정. "
            f"factuality={merged.get('factuality_score')}, "
            f"hallucination={merged.get('hallucination_score')}, "
            f"toxicity={merged.get('toxicity_score')}."
        )
        if merged.get("masking_applied"):
            detail += f" 마스킹 항목: {', '.join(merged.get('masking_labels') or [])}."
    elif node_name == "final_response":
        detail = f"사용자에게 보낼 최종 응답을 생성했습니다. action={merged.get('safety_action') or 'AUTO_RESPONSE'}"
    else:
        detail = f"상태 필드 {', '.join(sorted(node_update.keys()))}를 업데이트했습니다."

    return {
        "node": node_name,
        "title": title,
        "detail": detail,
        "updated_keys": sorted(node_update.keys()),
    }


def _print_node_summary(summary: dict[str, Any]) -> None:
    print(f"[노드 요약] {summary['title']}")
    print(f"  - {summary['detail']}")
    print(f"  - 업데이트: {', '.join(summary['updated_keys'])}")


def run_chatbot(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
    )
    result = graph.invoke(state, config=build_runnable_config(state, run_name="chatbot_request"))
    log_event(
        "langsmith_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_trace_metadata(result),
    )

    if os.getenv("CHATBOT_DEBUG_ROUTING", "").lower() in ("1", "true", "yes"):
        print("[routing_debug]")
        print(f"category: {result.get('category')}")
        print(f"routing_target: {result.get('routing_target')}")
        print(f"classification_method: {result.get('classification_method')}")
        print(f"classification_reason: {result.get('classification_reason')}")

    return {
        "answer": last_message_text(result),
        "state": result,
    }


def stream_chatbot(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
):
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
    )
    result: dict[str, Any] = {}
    node_summaries: list[dict[str, Any]] = []

    for chunk in graph.stream(
        state,
        config=build_runnable_config(state, run_name="chatbot_stream_request"),
        stream_mode="updates",
    ):
        for node_name, node_update in chunk.items():
            summary = _node_summary(node_name, node_update, {**state, **result})
            node_summaries.append(summary)
            _print_node_summary(summary)
            log_event(
                EVENT_NODE_COMPLETED,
                ticket_id=ticket_id,
                session_id=session_id,
                node_name=f"stream:{node_name}",
                status="stream_update",
                metadata={"updated_keys": sorted(node_update.keys())},
            )
            result.update(node_update)

    log_event(
        "langsmith_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_trace_metadata({**state, **result}),
    )

    return {
        "answer": last_message_text(result),
        "state": result,
        "input_state": state,
        "node_summaries": node_summaries,
    }
