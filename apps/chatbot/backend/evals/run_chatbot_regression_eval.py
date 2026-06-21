from __future__ import annotations

import argparse
import json
import os
import sys
import time
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
DATASET_DIR = Path(__file__).parent / "datasets"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-e2e-workflow-22-v1.json"
DEFAULT_OUTPUT = Path(__file__).parent / "outputs" / "gameops_chatbot_regression_eval.json"

for path in (PROJECT_ROOT, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.service.chatbot_service import stream_chatbot
from common.observability.langfuse import (
    build_trace_metadata,
    configure_langfuse,
    link_current_trace,
    observe_if_enabled,
)


configure_langfuse("chatbot", default_tags=["chatbot", "eval", "regression"])


CHATBOT_ROUTES = {"payment_agent", "bug_agent", "faq_agent", "voc_agent"}
CHATBOT_CATEGORIES = {"payment", "bug", "faq", "voc"}
UI_SUBCATEGORY_ROUTES = {
    "payment_history": ("payment", "payment_agent"),
    "missing_item": ("payment", "payment_agent"),
    "duplicate_payment": ("payment", "payment_agent"),
    "payment_method": ("faq", "faq_agent"),
    "refund_policy": ("faq", "faq_agent"),
    "login_issue": ("faq", "faq_agent"),
    "account_recovery": ("faq", "faq_agent"),
    "account_linking": ("faq", "faq_agent"),
    "phone_change": ("faq", "faq_agent"),
    "product_not_delivered": ("payment", "payment_agent"),
    "mail_reward": ("faq", "faq_agent"),
    "coupon_usage": ("faq", "faq_agent"),
    "launch_access_error": ("bug", "bug_agent"),
    "gameplay_progress_error": ("bug", "bug_agent"),
    "graphics_sound_error": ("bug", "bug_agent"),
    "paid_item_missing": ("payment", "payment_agent"),
    "reward_mail_missing": ("payment", "payment_agent"),
    "gacha_log_issue": ("payment", "payment_agent"),
    "notice_event": ("faq", "faq_agent"),
    "voc_etc": ("voc", "voc_agent"),
}
SOURCE_TYPE_EVIDENCE = {
    "hoyoverse_qna_common": "faq_document",
    "hoyoverse_qna_onlygenshin": "faq_document",
    "hoyoverse_policy": "policy_document",
    "naver_cafe_notice": "notice_document",
    "naver_cafe_guide": "game_guide",
}


def load_chatbot_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)


def load_examples(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def _resolve_eval_route(inputs: dict[str, Any]) -> tuple[str, str | None]:
    category = str(inputs.get("category") or "").strip()
    routing_target = inputs.get("routing_target")

    sub_category = str(inputs.get("sub_category") or "").strip()
    if not category and sub_category in UI_SUBCATEGORY_ROUTES:
        category, routing_target = UI_SUBCATEGORY_ROUTES[sub_category]

    if category and not routing_target:
        routing_target = {
            "payment": "payment_agent",
            "bug": "bug_agent",
            "faq": "faq_agent",
            "voc": "voc_agent",
        }.get(category)
    return category, routing_target


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


def _ragas_string_rubrics(rubrics: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in rubrics.items():
        if value is None:
            continue
        if isinstance(value, str):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = json.dumps(value, ensure_ascii=False, default=str)
    return normalized


def _ragas_metric_result(
    *,
    key: str,
    metric_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    if metric_name not in {"answer_relevancy", "instance_rubrics"} and not _requires_ragas(reference_outputs):
        return {"key": key, "value": "not_applicable"}

    answer = str(outputs.get("answer") or "").strip()
    reference = str(reference_outputs.get("reference_answer") or "").strip()
    rubrics = dict(reference_outputs.get("rubrics") or {})
    contexts = list(outputs.get("retrieved_contexts") or [])
    if not answer:
        return {"key": key, "value": "not_applicable"}
    if metric_name in {"factual_correctness", "context_precision", "context_recall"} and not reference:
        return {"key": key, "value": "not_applicable"}
    if metric_name == "instance_rubrics" and not rubrics:
        return {"key": key, "value": "not_applicable"}
    if metric_name in {"faithfulness", "context_precision", "context_recall"} and not contexts:
        return {"key": key, "score": 0.0, "value": "no_retrieved_contexts"}

    try:
        from ragas import SingleTurnSample
        from ragas.metrics import (
            FactualCorrectness,
            Faithfulness,
            InstanceRubrics,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
        )
        try:
            from ragas.metrics import AnswerRelevancy
        except ImportError:
            from ragas.metrics import ResponseRelevancy

            AnswerRelevancy = ResponseRelevancy
    except ImportError:
        return {"key": key, "value": "not_applicable"}

    metric_by_name = {
        "factual_correctness": FactualCorrectness,
        "answer_relevancy": AnswerRelevancy,
        "faithfulness": Faithfulness,
        "context_precision": LLMContextPrecisionWithReference,
        "context_recall": LLMContextRecall,
        "instance_rubrics": InstanceRubrics,
    }
    metric = metric_by_name[metric_name]()
    judges = _ragas_judges()
    if hasattr(metric, "llm"):
        metric.llm = judges["llm"]
    if hasattr(metric, "embeddings"):
        metric.embeddings = judges["embeddings"]

    sample_kwargs = {
        "user_input": str(inputs.get("user_message") or ""),
        "response": answer,
        "reference": reference,
        "retrieved_contexts": contexts,
    }
    if metric_name == "instance_rubrics":
        sample_kwargs["rubrics"] = _ragas_string_rubrics(rubrics)
    sample = SingleTurnSample(**sample_kwargs)
    try:
        score = metric.single_turn_score(sample)
    except AttributeError:
        import asyncio

        score = asyncio.run(metric.single_turn_ascore(sample))
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


def answer_relevancy(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="answer_relevancy",
        metric_name="answer_relevancy",
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


def instance_rubrics(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _ragas_metric_result(
        key="instance_rubrics",
        metric_name="instance_rubrics",
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


def invalid_category_handling(outputs: dict[str, Any]) -> dict[str, Any]:
    category = str(outputs.get("category") or "")
    if category in CHATBOT_CATEGORIES:
        return {"key": "invalid_category_handling", "value": "not_applicable"}
    handled = (
        outputs.get("route") == "out_of_chatbot_scope"
        and outputs.get("routing_target") == "external_system"
        and outputs.get("safety_action") == "REVIEW_REQUIRED"
    )
    return {
        "key": "invalid_category_handling",
        "score": handled,
        "value": {
            "category": category,
            "route": outputs.get("route"),
            "routing_target": outputs.get("routing_target"),
            "safety_action": outputs.get("safety_action"),
        },
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


def chatbot_target(inputs: dict[str, Any]) -> dict[str, Any]:
    category, routing_target = _resolve_eval_route(inputs)
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
            "observed_evidence_types": [],
            "retrieved_contexts": [],
        }
    if not inputs.get("user_message"):
        return {
            "answer": "",
            "route": routing_target,
            "category": category,
            "routing_target": routing_target,
            "safety_action": "AUTO_RESPONSE",
            "safety_passed": None,
            "cache_events": [],
            "redis_cache_hit_observed": False,
            "redis_cache_store_backend": None,
            "latency_ms": 0.0,
            "retrieved_document_count": 0,
            "observed_evidence_types": [],
            "retrieved_contexts": [],
        }

    raw_account_id = inputs.get("account_id")
    account_id = int(raw_account_id) if category == "payment" and raw_account_id not in (None, "") else None
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
            category=category,
            user_id=user_id,
            account_id=account_id,
            ui_category=inputs.get("ui_category"),
            sub_category=inputs.get("sub_category"),
            routing_target=routing_target,
            fallback_routing_target=inputs.get("fallback_routing_target"),
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
        "observed_evidence_types": observed_evidence_types,
    }


Evaluator = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]


def _run_output_only(metric: Callable[[dict[str, Any]], dict[str, Any]], outputs: dict[str, Any]) -> dict[str, Any]:
    return metric(outputs)


def _evaluate_example(
    *,
    index: int,
    inputs: dict[str, Any],
    reference_outputs: dict[str, Any],
    evaluators: list[Evaluator],
) -> dict[str, Any]:
    outputs = chatbot_target(inputs)
    metrics = [evaluator(inputs, outputs, reference_outputs) for evaluator in evaluators]
    return {
        "example_index": index,
        "inputs": inputs,
        "reference_outputs": reference_outputs,
        "outputs": outputs,
        "metrics": metrics,
    }


def _summarize_metric(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [metric for metric in metrics if "score" in metric]
    passed = [metric for metric in scored if bool(metric.get("score"))]
    numeric_scores = [
        float(metric["score"])
        for metric in scored
        if isinstance(metric.get("score"), (int, float))
    ]
    return {
        "count": len(metrics),
        "scored_count": len(scored),
        "pass_count": len(passed),
        "avg_score": round(sum(numeric_scores) / len(numeric_scores), 4) if numeric_scores else None,
    }


@observe_if_enabled(
    name="chatbot_regression_eval",
    as_type="chain",
    tags=["chatbot", "eval", "regression"],
)
def run_regression_eval(
    *,
    dataset_path: Path,
    output_path: Path,
    limit: int | None,
    test_type: str | None,
    eval_slice: str | None,
    enable_ragas: bool,
) -> dict[str, Any]:
    dataset_info, examples = load_examples(dataset_path)
    if test_type:
        examples = [example for example in examples if (example.get("metadata") or {}).get("test_type") == test_type]
    if eval_slice:
        examples = [example for example in examples if (example.get("metadata") or {}).get("eval_slice") == eval_slice]
    if limit is not None:
        examples = examples[:limit]

    evaluators: list[Evaluator] = [
        lambda inputs, outputs, ref: route_accuracy(outputs, ref),
        lambda inputs, outputs, ref: tool_db_call_accuracy(outputs, ref),
        lambda inputs, outputs, ref: safety_pass_accuracy(outputs, ref),
        lambda inputs, outputs, ref: latency(outputs),
        lambda inputs, outputs, ref: invalid_category_handling(outputs),
        lambda inputs, outputs, ref: action_match(outputs, ref),
        lambda inputs, outputs, ref: answer_non_empty(outputs),
        lambda inputs, outputs, ref: instance_rubrics(inputs, outputs, ref),
        lambda inputs, outputs, ref: redis_cache_observed(outputs, ref),
    ]
    if enable_ragas and find_spec("ragas") is not None:
        evaluators[1:1] = [
            answer_correctness,
            answer_relevancy,
            faithfulness,
            context_precision,
            context_recall,
        ]

    link_current_trace(
        tags=["chatbot", "eval", "regression"],
        metadata=build_trace_metadata(
            {},
            dataset_path=str(dataset_path),
            example_count=len(examples),
            test_type=test_type,
            eval_slice=eval_slice,
            enable_ragas=enable_ragas,
        ),
        input_payload={
            "dataset_path": str(dataset_path),
            "limit": limit,
            "test_type": test_type,
            "eval_slice": eval_slice,
            "enable_ragas": enable_ragas,
        },
    )

    results = []
    for index, example in enumerate(examples, start=1):
        results.append(
            _evaluate_example(
                index=index,
                inputs=dict(example.get("inputs") or {}),
                reference_outputs=dict(example.get("outputs") or {}),
                evaluators=evaluators,
            )
        )

    metric_groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        for metric in result["metrics"]:
            metric_groups.setdefault(str(metric["key"]), []).append(metric)

    report = {
        "dataset": dataset_info.get("dataset_info") or {"path": str(dataset_path)},
        "summary": {key: _summarize_metric(values) for key, values in sorted(metric_groups.items())},
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    link_current_trace(
        tags=["chatbot", "eval", "regression"],
        metadata=build_trace_metadata({}, output_path=str(output_path), evaluated_count=len(results)),
        output_payload={
            "output_path": str(output_path),
            "evaluated_count": len(results),
            "metric_keys": sorted(metric_groups),
        },
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local chatbot regression evaluation with Langfuse tracing.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--test-type")
    parser.add_argument("--eval-slice")
    parser.add_argument("--enable-ragas", action="store_true")
    parser.add_argument("--disable-retrieval-cache", action="store_true")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument(
        "--cache-namespace",
        choices=["answer", "retrieval", "all"],
        default="all",
    )
    args = parser.parse_args()

    load_chatbot_env()
    os.environ.setdefault("CHATBOT_DEBUG_ROUTING", "false")
    if args.disable_retrieval_cache:
        os.environ["FAQ_RETRIEVAL_CACHE_ENABLED"] = "false"

    if args.clear_cache:
        from common.retrieval.cache_store import clear_faq_cache

        namespace = None if args.cache_namespace == "all" else args.cache_namespace
        print(f"Cleared FAQ cache: {clear_faq_cache(namespace)}")

    report = run_regression_eval(
        dataset_path=args.dataset,
        output_path=args.output,
        limit=args.limit,
        test_type=args.test_type,
        eval_slice=args.eval_slice,
        enable_ragas=args.enable_ragas,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
