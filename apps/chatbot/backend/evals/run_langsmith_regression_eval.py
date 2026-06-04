from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import evaluate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = PROJECT_ROOT.parents[2] / "packages" / "common-python" / "src"
for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.service.chatbot_service import stream_chatbot


CHATBOT_ROUTES = {"payment_agent", "bug_agent", "faq_agent", "voc_agent"}
CHATBOT_CATEGORIES = {"payment", "bug", "faq", "voc"}


def load_chatbot_langsmith_env() -> None:
    """Load repo .env and map chatbot-specific LangSmith env names to SDK names."""
    load_dotenv(REPO_ROOT / ".env", override=True)
    mappings = {
        "CHATBOT_LANGSMITH_API_KEY": "LANGSMITH_API_KEY",
        "CHATBOT_LANGSMITH_PROJECT": "LANGSMITH_PROJECT",
        "CHATBOT_LANGSMITH_TRACING": "LANGSMITH_TRACING",
    }
    for source, target in mappings.items():
        value = os.environ.get(source)
        if value:
            os.environ[target] = value
    if os.environ.get("LANGSMITH_TRACING"):
        os.environ["LANGCHAIN_TRACING_V2"] = os.environ["LANGSMITH_TRACING"]


def chatbot_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run the chatbot workflow for one LangSmith dataset example."""
    category = str(inputs.get("category") or "")
    if category not in CHATBOT_CATEGORIES:
        return {
            "answer": "",
            "route": "out_of_chatbot_scope",
            "category": category,
            "routing_target": "external_system",
            "safety_action": "REVIEW_REQUIRED",
            "safety_passed": None,
            "cache_events": [],
            "redis_cache_hit_observed": False,
            "redis_cache_store_backend": None,
            "latency_ms": 0.0,
            "retrieved_document_count": 0,
            "payment_context_count": 0,
            "payment_context_counts": {},
            "faq_failure_reason": None,
            "observed_evidence_types": [],
        }

    account_id = int(inputs.get("account_id") or 0)
    user_id = int(inputs.get("user_id") or 0)
    ticket_id = int(inputs.get("ticket_id") or int(time.time() * 1000) % 1_000_000_000)

    from chatbot.generation import faq_agent

    cache_events: list[dict[str, Any]] = []
    original_log_event = faq_agent.log_event

    def capture_log_event(event_type: str, **kwargs: Any) -> Any:
        if kwargs.get("tool_name") == "faq_retrieval_cache":
            cache_events.append(dict(kwargs.get("metadata") or {}))
        return original_log_event(event_type, **kwargs)

    faq_agent.log_event = capture_log_event
    try:
        started_at = time.perf_counter()
        result = stream_chatbot(
            ticket_id=ticket_id,
            user_message=str(inputs["user_message"]),
            category=inputs.get("category"),
            user_id=user_id,
            account_id=account_id,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
    finally:
        faq_agent.log_event = original_log_event

    state = result.get("state") or {}
    retrieved_documents = state.get("retrieved_documents") or []
    payment_context = state.get("payment_context") or {}
    payment_counts = payment_context.get("counts") or {}
    observed_evidence_types = _observed_evidence_types(
        retrieved_documents=retrieved_documents,
        payment_counts=payment_counts,
        route=state.get("reasoning_node"),
    )
    return {
        "answer": result.get("answer"),
        "route": state.get("reasoning_node"),
        "category": state.get("category"),
        "routing_target": state.get("routing_target"),
        "safety_action": state.get("safety_action"),
        "safety_passed": state.get("safety_passed"),
        "cache_events": cache_events,
        "redis_cache_hit_observed": any(event.get("cache_hit") for event in cache_events),
        "redis_cache_store_backend": next(
            (event.get("cache_backend") for event in cache_events if event.get("cache_backend")),
            None,
        ),
        "latency_ms": latency_ms,
        "retrieved_document_count": len(retrieved_documents),
        "payment_context_count": payment_context.get("count", 0),
        "payment_context_counts": payment_counts,
        "faq_failure_reason": state.get("faq_failure_reason"),
        "observed_evidence_types": observed_evidence_types,
    }


def _observed_evidence_types(
    *,
    retrieved_documents: list[dict[str, Any]],
    payment_counts: dict[str, Any],
    route: str | None,
) -> list[str]:
    observed: set[str] = set()
    if retrieved_documents:
        observed.update({"faq_document", "policy_document", "notice_document", "game_guide"})
    for evidence_type in ("payments", "refunds", "item_delivery_logs", "gacha_logs"):
        if int(payment_counts.get(evidence_type) or 0) > 0:
            observed.add(evidence_type)
    if route == "bug_agent":
        observed.add("bug_report_context")
    return sorted(observed)


def _required_evidence(reference_outputs: dict[str, Any]) -> list[str]:
    return list(reference_outputs.get("required_evidence_types") or [])


def _evidence_match(required: list[str], observed: list[str]) -> tuple[int, int]:
    required_set = set(required)
    observed_set = set(observed)
    if not required_set:
        return 0, 0
    return len(required_set & observed_set), len(required_set)


def route_accuracy(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    expected = reference_outputs.get("expected_route")
    if expected == "dashboard_or_cs_agent":
        return {"key": "route_accuracy", "score": outputs.get("route") == "out_of_chatbot_scope"}
    if expected not in CHATBOT_ROUTES:
        return {"key": "route_accuracy", "value": "not_applicable"}
    return {"key": "route_accuracy", "score": outputs.get("route") == expected}


def action_match(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    expected = reference_outputs.get("expected_action")
    if expected == "AUTO_RESPONSE":
        actual_ok = outputs.get("safety_action") in (None, "AUTO_RESPONSE", "PASS", "MASKING")
    elif expected == "REVIEW_REQUIRED":
        actual_ok = outputs.get("safety_action") in {
            "REVIEW_REQUIRED",
            "REVIEW_QUEUE",
            "BLOCK_RESPONSE",
            "SAFE_FALLBACK",
        }
    elif expected == "SAFE_FALLBACK":
        actual_ok = outputs.get("safety_action") in {"SAFE_FALLBACK", "BLOCK_RESPONSE"}
    else:
        return {"key": "action_match", "value": "not_applicable"}
    return {"key": "action_match", "score": actual_ok}


def answer_non_empty(outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "answer_non_empty", "score": bool(str(outputs.get("answer") or "").strip())}


def answer_correctness(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Lightweight reference-overlap proxy; use LLM/RAGAS judges for stricter scoring."""
    answer = str(outputs.get("answer") or "")
    reference = str(reference_outputs.get("reference_answer") or "")
    keywords = [word for word in reference.replace(",", " ").replace(".", " ").split() if len(word) >= 3]
    if not keywords:
        return {"key": "answer_correctness", "value": "not_applicable"}
    hits = sum(1 for word in keywords if word in answer)
    score = hits / len(keywords)
    return {"key": "answer_correctness", "score": score, "value": round(score, 3)}


def faithfulness(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    required = _required_evidence(reference_outputs)
    if not required:
        return {"key": "faithfulness", "value": "not_applicable"}
    observed_hits, required_count = _evidence_match(required, outputs.get("observed_evidence_types") or [])
    grounded = observed_hits > 0 and bool(str(outputs.get("answer") or "").strip())
    if outputs.get("faq_failure_reason") in {"no_retrieved_documents", "empty_retrieved_documents"}:
        grounded = False
    return {"key": "faithfulness", "score": grounded, "value": f"{observed_hits}/{required_count}"}


def context_precision(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    if not reference_outputs.get("required_evidence_types"):
        return {"key": "context_precision", "value": "not_applicable"}
    observed = outputs.get("observed_evidence_types") or []
    if not observed:
        return {"key": "context_precision", "score": 0.0, "value": "0/0"}
    required = set(_required_evidence(reference_outputs))
    hits = sum(1 for evidence_type in observed if evidence_type in required)
    score = hits / len(observed)
    return {"key": "context_precision", "score": score, "value": f"{hits}/{len(observed)}"}


def context_recall(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    required = _required_evidence(reference_outputs)
    if not required:
        return {"key": "context_recall", "value": "not_applicable"}
    hits, total = _evidence_match(required, outputs.get("observed_evidence_types") or [])
    score = hits / total
    return {"key": "context_recall", "score": score, "value": f"{hits}/{total}"}


def tool_db_call_accuracy(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    required = [
        evidence
        for evidence in _required_evidence(reference_outputs)
        if evidence in {"payments", "refunds", "item_delivery_logs", "gacha_logs"}
    ]
    if not required:
        return {"key": "tool_db_call_accuracy", "value": "not_applicable"}
    hits, total = _evidence_match(required, outputs.get("observed_evidence_types") or [])
    return {"key": "tool_db_call_accuracy", "score": hits / total, "value": f"{hits}/{total}"}


def safety_pass_accuracy(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    result = action_match(outputs, reference_outputs)
    if "score" not in result:
        return {"key": "safety_pass_accuracy", "value": "not_applicable"}
    return {"key": "safety_pass_accuracy", "score": result["score"]}


def latency(outputs: dict[str, Any]) -> dict[str, Any]:
    latency_ms = float(outputs.get("latency_ms") or 0)
    target_ms = float(os.environ.get("EVAL_LATENCY_TARGET_MS", "30000"))
    return {"key": "latency", "score": latency_ms <= target_ms, "value": round(latency_ms, 1)}


def cost(outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": "cost",
        "value": "not_available_from_code_evaluator; check LangSmith trace token/cost fields",
    }


def redis_cache_observed(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    expected = reference_outputs.get("expected_cache_behavior")
    if expected == "retrieval_cache_hit":
        return {"key": "redis_cache_observed", "score": bool(outputs.get("redis_cache_hit_observed"))}
    if expected == "warmup_miss_then_store":
        return {
            "key": "redis_cache_observed",
            "score": bool(outputs.get("redis_cache_store_backend") in {"redis", "memory"}),
            "value": outputs.get("redis_cache_store_backend"),
        }
    return {"key": "redis_cache_observed", "value": "not_applicable"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LangSmith regression evaluation for the chatbot.")
    parser.add_argument("--dataset-name", default="gameops-chatbot-regression-v1")
    parser.add_argument("--experiment-prefix", default="gameops-chatbot-regression")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--limit", type=int, help="Evaluate only the first N examples after slicing locally.")
    parser.add_argument("--test-type", help="Evaluate only examples whose metadata.test_type matches this value.")
    args = parser.parse_args()

    load_chatbot_langsmith_env()
    os.environ.setdefault("CHATBOT_DEBUG_ROUTING", "false")

    data: Any = args.dataset_name
    if args.limit is not None or args.test_type:
        from langsmith import Client

        client = Client()
        examples = list(client.list_examples(dataset_name=args.dataset_name))
        if args.test_type:
            examples = [example for example in examples if (example.metadata or {}).get("test_type") == args.test_type]
        if args.limit is not None:
            examples = examples[: args.limit]
        data = examples

    results = evaluate(
        chatbot_target,
        data=data,
        evaluators=[
            route_accuracy,
            answer_correctness,
            faithfulness,
            context_precision,
            context_recall,
            tool_db_call_accuracy,
            safety_pass_accuracy,
            latency,
            cost,
            action_match,
            answer_non_empty,
            redis_cache_observed,
        ],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=args.max_concurrency,
    )
    print(results)


if __name__ == "__main__":
    main()
