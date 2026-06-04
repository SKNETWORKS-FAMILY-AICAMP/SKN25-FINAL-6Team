from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from functools import lru_cache
from importlib.util import find_spec
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
SOURCE_TYPE_EVIDENCE = {
    "hoyoverse_qna_common": "faq_document",
    "hoyoverse_qna_onlygenshin": "faq_document",
    "hoyoverse_policy": "policy_document",
    "naver_cafe_notice": "notice_document",
    "naver_cafe_guide": "game_guide",
}


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
            "retrieved_contexts": [],
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
        cache_events=cache_events,
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
        "retrieved_contexts": _retrieved_contexts(retrieved_documents),
        "payment_context_count": payment_context.get("count", 0),
        "payment_context_counts": payment_counts,
        "faq_failure_reason": state.get("faq_failure_reason"),
        "observed_evidence_types": observed_evidence_types,
    }


def _retrieved_contexts(retrieved_documents: list[dict[str, Any]]) -> list[str]:
    contexts = []
    for document in retrieved_documents:
        text = document.get("chunk_text") or document.get("content") or document.get("text")
        if text:
            contexts.append(str(text))
    return contexts


def _observed_evidence_types(
    *,
    retrieved_documents: list[dict[str, Any]],
    payment_counts: dict[str, Any],
    route: str | None,
    cache_events: list[dict[str, Any]],
) -> list[str]:
    observed: set[str] = set()
    for document in retrieved_documents:
        source_type = str(document.get("source_type") or "")
        if source_type in SOURCE_TYPE_EVIDENCE:
            observed.add(SOURCE_TYPE_EVIDENCE[source_type])
        elif source_type in {"payments", "refunds", "item_delivery_logs", "gacha_logs"}:
            observed.add(source_type)
    for evidence_type in ("payments", "refunds", "item_delivery_logs", "gacha_logs"):
        if int(payment_counts.get(evidence_type) or 0) > 0:
            observed.add(evidence_type)
    if route == "bug_agent":
        observed.add("bug_report_context")
    if cache_events:
        observed.add("redis_retrieval_cache")
    return sorted(observed)


def _required_evidence(reference_outputs: dict[str, Any]) -> list[str]:
    return list(reference_outputs.get("required_evidence_types") or [])


def _requires_ragas(reference_outputs: dict[str, Any]) -> bool:
    if reference_outputs.get("requires_rag"):
        return True
    rag_evidence = {
        "faq_document",
        "policy_document",
        "notice_document",
        "game_guide",
        "redis_retrieval_cache",
    }
    return bool(rag_evidence & set(_required_evidence(reference_outputs)))


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


@lru_cache(maxsize=1)
def _ragas_judges() -> dict[str, Any]:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)

    llm_model = os.environ.get("RAGAS_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    embedding_model = os.environ.get("RAGAS_EMBEDDING_MODEL") or os.environ.get(
        "EMBEDDING_MODEL",
        "text-embedding-3-small",
    )
    if embedding_model.startswith("openai:"):
        embedding_model = embedding_model.split(":", 1)[1]

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    return {
        "llm": LangchainLLMWrapper(ChatOpenAI(model=llm_model, api_key=api_key, temperature=0)),
        "embeddings": LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=embedding_model, api_key=api_key)),
    }


def _ragas_metric_result(
    *,
    key: str,
    metric_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    if not _requires_ragas(reference_outputs):
        return {"key": key, "value": "not_applicable"}

    answer = str(outputs.get("answer") or "").strip()
    reference = str(reference_outputs.get("reference_answer") or "").strip()
    contexts = list(outputs.get("retrieved_contexts") or [])
    if not answer or not reference:
        return {"key": key, "value": "not_applicable"}
    if metric_name != "factual_correctness" and not contexts:
        return {"key": key, "score": 0.0, "value": "no_retrieved_contexts"}

    try:
        from ragas import SingleTurnSample
        from ragas.metrics import (
            FactualCorrectness,
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
        )
    except ImportError:
        return {"key": key, "value": "not_applicable"}

    metric_by_name = {
        "factual_correctness": FactualCorrectness,
        "faithfulness": Faithfulness,
        "context_precision": LLMContextPrecisionWithReference,
        "context_recall": LLMContextRecall,
    }
    metric_cls = metric_by_name[metric_name]
    metric = metric_cls()
    judges = _ragas_judges()
    if hasattr(metric, "llm"):
        metric.llm = judges["llm"]
    if hasattr(metric, "embeddings"):
        metric.embeddings = judges["embeddings"]

    sample = SingleTurnSample(
        user_input=str(inputs.get("user_message") or ""),
        response=answer,
        reference=reference,
        retrieved_contexts=contexts,
    )
    try:
        score = asyncio.run(metric.single_turn_ascore(sample))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            score = loop.run_until_complete(metric.single_turn_ascore(sample))
        finally:
            loop.close()
    except Exception as exc:
        return {"key": key, "value": f"ragas_error:{type(exc).__name__}"}
    return {"key": key, "score": float(score), "value": round(float(score), 3)}


def answer_correctness(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="answer_correctness",
        metric_name="factual_correctness",
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )


def faithfulness(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="faithfulness",
        metric_name="faithfulness",
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )


def context_precision(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="context_precision",
        metric_name="context_precision",
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )


def context_recall(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="context_recall",
        metric_name="context_recall",
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )


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
    parser.add_argument("--enable-ragas", action="store_true", help="Run RAGAS judge metrics for RAG examples.")
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

    evaluators = [
        route_accuracy,
        tool_db_call_accuracy,
        safety_pass_accuracy,
        latency,
        action_match,
        answer_non_empty,
        redis_cache_observed,
    ]
    if args.enable_ragas and find_spec("ragas") is not None:
        evaluators[1:1] = [
            answer_correctness,
            faithfulness,
            context_precision,
            context_recall,
        ]
    elif args.enable_ragas:
        print("Skipped RAGAS evaluators: ragas is not installed.")

    results = evaluate(
        chatbot_target,
        data=data,
        evaluators=evaluators,
        experiment_prefix=args.experiment_prefix,
        max_concurrency=args.max_concurrency,
    )
    print(results)


if __name__ == "__main__":
    main()
