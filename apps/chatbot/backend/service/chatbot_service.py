from __future__ import annotations

import os
from typing import Any

from chatbot.observability.langsmith import build_runnable_config, build_trace_metadata
from chatbot.observability.logger import EVENT_NODE_COMPLETED, log_event


def build_state(
    ticket_id: int,
    user_message: str,
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
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
        "category": category or "",
        "routing_target": "",
        "classification_method": None,
        "classification_reason": None,
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
        "turn_count": len([message for message in messages if message.get("role") == "user"]),
    }


def last_message_text(result: dict[str, Any]) -> str:
    final_text = result.get("final_text")
    if final_text:
        return str(final_text)
    raise RuntimeError("chatbot workflow completed without final_text")


def _node_summary(node_name: str, node_update: dict[str, Any], state_snapshot: dict[str, Any]) -> dict[str, Any]:
    merged = {**state_snapshot, **node_update}
    title_by_node = {
        "ticket_preprocess": "Ticket preprocess",
        "payment_agent": "Payment agent",
        "bug_agent": "Bug agent",
        "faq_agent": "FAQ/RAG",
        "voc_agent": "VOC agent",
        "draft_persistence": "State draft",
        "safety_layer": "Safety check",
        "final_response": "Final response",
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
        query = merged.get("retrieval_query") or merged.get("enriched_query") or merged.get("raw_query")
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
    elif node_name == "final_response":
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


def run_chatbot(
    ticket_id: int,
    user_message: str,
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
) -> dict[str, Any]:
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        category=category,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
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
    category: str | None = None,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
    conversation_summary: str | None = None,
):
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        category=category,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
        conversation_summary=conversation_summary,
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
