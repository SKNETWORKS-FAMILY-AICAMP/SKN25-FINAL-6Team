from __future__ import annotations

import os
from typing import Any

from constants import DEFAULT_DEMO_USER_ID
from observability.langfuse import build_chatbot_trace_metadata
from observability.logger import EVENT_NODE_COMPLETED, log_event
from utils.input_preprocessing import preprocess_user_input
from common.observability.langfuse import get_langchain_config, link_current_trace, observe_if_enabled, trace_attributes


def build_state(
    ticket_id: int,
    user_message: str,
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = DEFAULT_DEMO_USER_ID,
    session_id: str = "1-1",
    source_type: str = "chatbot",
    ui_category: str | None = None,
    sub_category: str | None = None,
    routing_target: str | None = None,
    fallback_routing_target: str | None = None,
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
    initial_bug_query: str | None = None,
    bug_report_form: str | None = None,
) -> dict[str, Any]:
    # 1단계: 사용자 입력을 마스킹/정규화 준비하고 LangGraph가 공유할 초기 state를 만든다.
    preprocessing = preprocess_user_input(user_message)
    masked_content = preprocessing["masked_content"]
    messages = list(previous_messages or [])
    messages.append({
        "role": "user",
        "content": (
            f"ticket_id={ticket_id}\n"
            f"account_id={account_id}\n"
            f"source_type={source_type}\n\n"
            f"Selected UI category: {ui_category or category or 'unknown'}\n"
            f"Selected subcategory: {sub_category or 'none'}\n"
            f"Selected routing target: {routing_target or 'none'}\n\n"
            f"Customer inquiry:\n{masked_content}"
        ),
    })

    return {
        "messages": messages,
        "previous_messages": list(previous_messages or []),
        "user_id": user_id,
        "session_id": session_id,
        "account_id": account_id,
        "source_type": source_type,
        "raw_query": user_message,
        "masked_content": masked_content,
        "input_masked": preprocessing["masked"],
        "input_detected_labels": preprocessing["detected_labels"],
        "normalized_query": None,
        "ticket_id": ticket_id,
        "category": category or "",
        "ui_category": ui_category,
        "sub_category": sub_category,
        "routing_target": routing_target or "",
        "fallback_routing_target": fallback_routing_target,
        "draft_id": None,
        "draft_text": None,
        "final_text": None,
        "reasoning_node": None,
        "safety_passed": None,
        "safety_action": None,
        "safety_reason": None,
        "review_required": None,
        "retry_count": 0,
        "conversation_summary": conversation_summary,
        "initial_bug_query": initial_bug_query,
        "bug_report_form": bug_report_form,
        "github_issue_content": None,
        "turn_count": len([message for message in messages if message.get("role") == "user"]),
    }


def last_message_text(result: dict[str, Any]) -> str:
    # workflow가 끝난 뒤 사용자에게 반환할 최종 응답만 꺼낸다.
    final_text = result.get("final_text")
    if final_text:
        return str(final_text)
    raise RuntimeError("chatbot workflow completed without final_text")


def _node_summary(node_name: str, node_update: dict[str, Any], state_snapshot: dict[str, Any]) -> dict[str, Any]:
    # stream 실행 중 각 노드가 무엇을 했는지 콘솔/로그용 요약 문장으로 변환한다.
    merged = {**state_snapshot, **node_update}
    title_by_node = {
        "ticket_preprocess": "Ticket preprocess",
        "payment_agent": "Payment agent",
        "bug_agent": "Bug agent",
        "faq_agent": "FAQ/RAG",
        "voc_agent": "VOC agent",
        "draft_persistence": "State draft",
        "safety_layer": "Safety check",
        "ticket_completion": "Ticket completion",
    }
    title = title_by_node.get(node_name, node_name)

    if node_name == "ticket_preprocess":
        detail = (
            f"Using user-selected category {merged.get('category') or 'unknown'} "
            f"with routing_target={merged.get('routing_target') or 'unknown'}."
        )
    elif node_name == "faq_agent":
        docs = merged.get("retrieved_documents") or []
        failure = merged.get("faq_failure_reason")
        query = (
            merged.get("retrieval_query")
            or merged.get("normalized_query")
            or merged.get("raw_query")
        )
        if failure:
            detail = f"FAQ search for '{query}' did not have enough evidence: {failure}."
        else:
            detail = f"FAQ search for '{query}' used {len(docs)} evidence documents."
    elif node_name == "payment_agent":
        detail = "Built a payment answer from chatbot state and scoped payment context."
    elif node_name == "bug_agent":
        detail = "Built a bug answer from chatbot state."
    elif node_name == "voc_agent":
        detail = "Prepared a VOC response in chatbot state."
    elif node_name == "draft_persistence":
        detail = f"Persisted draft/evidence. evidence_count={merged.get('evidence_count', 0)}."
    elif node_name == "safety_layer":
        detail = (
            f"{merged.get('safety_action') or 'UNKNOWN'} decision. "
            f"factuality={merged.get('factuality_score')}, "
            f"hallucination={merged.get('hallucination_score')}, "
            f"toxicity={merged.get('toxicity_score')}."
        )
        if merged.get("masking_applied"):
            detail += f" masking_labels={', '.join(merged.get('masking_labels') or [])}."
    elif node_name == "ticket_completion":
        detail = f"Persisted final response. action={merged.get('safety_action') or 'AUTO_RESPONSE'}."
    else:
        detail = f"Updated state fields: {', '.join(sorted(node_update.keys()))}."

    return {
        "node": node_name,
        "title": title,
        "detail": detail,
        "updated_keys": sorted(node_update.keys()),
    }


def _print_node_summary(summary: dict[str, Any]) -> None:
    print(f"[node] {summary['title']}")
    print(f"  - {summary['detail']}")
    print(f"  - updated: {', '.join(summary['updated_keys'])}")


def _chat_trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "inquiry": inputs.get("user_message"),
    }


def _chat_trace_outputs(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": output.get("answer"),
    }


@observe_if_enabled(
    name="chatbot_request",
    as_type="chain",
    tags=["chatbot", "feature:generation"],
)
def run_chatbot(
    ticket_id: int,
    user_message: str,
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = DEFAULT_DEMO_USER_ID,
    session_id: str = "1-1",
    source_type: str = "chatbot",
    ui_category: str | None = None,
    sub_category: str | None = None,
    routing_target: str | None = None,
    fallback_routing_target: str | None = None,
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
    initial_bug_query: str | None = None,
    bug_report_form: str | None = None,
) -> dict[str, Any]:
    # 동기 실행 경로: 초기 state 생성 -> graph.invoke -> 최종 답변 반환.
    from chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        category=category,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        ui_category=ui_category,
        sub_category=sub_category,
        routing_target=routing_target,
        fallback_routing_target=fallback_routing_target,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
        initial_bug_query=initial_bug_query,
        bug_report_form=bug_report_form,
    )
    trace_metadata = build_chatbot_trace_metadata(state)
    with trace_attributes(
        user_id=user_id,
        session_id=session_id,
        tags=["chatbot", "feature:generation"],
        metadata=trace_metadata,
    ):
        link_current_trace(
            user_id=user_id,
            session_id=session_id,
            tags=["chatbot", "feature:generation"],
            metadata=trace_metadata,
            input_payload=_chat_trace_inputs({"user_message": user_message}),
        )
        result = graph.invoke(state, config=get_langchain_config())
    log_event(
        "langfuse_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_chatbot_trace_metadata(result),
    )
    link_current_trace(
        user_id=user_id,
        session_id=session_id,
        tags=["chatbot", "feature:generation", "feature:persistence"],
        metadata=build_chatbot_trace_metadata(result),
        output_payload=_chat_trace_outputs({"answer": last_message_text(result)}),
    )

    if os.getenv("CHATBOT_DEBUG_ROUTING", "").lower() in ("1", "true", "yes"):
        print("[routing_debug]")
        print(f"category: {result.get('category')}")
        print(f"routing_target: {result.get('routing_target')}")

    return {
        "answer": last_message_text(result),
        "state": result,
    }


@observe_if_enabled(
    name="chatbot_stream_request",
    as_type="chain",
    tags=["chatbot", "feature:generation", "feature:stream"],
)
def stream_chatbot(
    ticket_id: int,
    user_message: str,
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = DEFAULT_DEMO_USER_ID,
    session_id: str = "1-1",
    source_type: str = "chatbot",
    ui_category: str | None = None,
    sub_category: str | None = None,
    routing_target: str | None = None,
    fallback_routing_target: str | None = None,
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
    initial_bug_query: str | None = None,
    bug_report_form: str | None = None,
):
    # 스트리밍 실행 경로: graph.stream의 노드별 update를 누적하면서 진행 상황을 기록한다.
    from chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        category=category,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        ui_category=ui_category,
        sub_category=sub_category,
        routing_target=routing_target,
        fallback_routing_target=fallback_routing_target,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
        initial_bug_query=initial_bug_query,
        bug_report_form=bug_report_form,
    )
    trace_metadata = build_chatbot_trace_metadata(state)
    link_current_trace(
        user_id=user_id,
        session_id=session_id,
        tags=["chatbot", "feature:generation", "feature:stream"],
        metadata=trace_metadata,
        input_payload=_chat_trace_inputs({"user_message": user_message}),
    )
    result: dict[str, Any] = {}
    node_summaries: list[dict[str, Any]] = []

    with trace_attributes(
        user_id=user_id,
        session_id=session_id,
        tags=["chatbot", "feature:generation", "feature:stream"],
        metadata=trace_metadata,
    ):
        for chunk in graph.stream(
            state,
            config=get_langchain_config(),
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
        "langfuse_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_chatbot_trace_metadata({**state, **result}),
    )
    link_current_trace(
        user_id=user_id,
        session_id=session_id,
        tags=["chatbot", "feature:generation", "feature:stream"],
        metadata=build_chatbot_trace_metadata({**state, **result}),
        output_payload=_chat_trace_outputs({"answer": last_message_text(result)}),
    )

    return {
        "answer": last_message_text(result),
        "state": result,
        "input_state": state,
        "node_summaries": node_summaries,
    }
