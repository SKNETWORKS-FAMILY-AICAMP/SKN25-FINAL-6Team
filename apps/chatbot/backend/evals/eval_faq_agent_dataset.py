from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
for path in (PROJECT_ROOT, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.generation.faq_agent import run_faq_rag
from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from common.observability.logger import estimate_tokens, record_usage, summarize_usage, usage_tracking_context


DATASET_DIR = Path(__file__).parent / "datasets"
OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-faq-agent-db-grounded-40-v1.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "gameops_faq_agent_eval_v1.json"

UNANSWERABLE_PATTERNS = (
    r"확인할 수 없",
    r"찾을 수 없",
    r"제공된 (자료|증거|정보).*없",
    r"구체적인 (안내|정보|지침).*없",
    r"포함되어 있지 않",
    r"추가적인 정보",
    r"특정.*필요",
    r"공식 커뮤니티",
    r"고객 지원",
)


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def make_state(example: dict[str, Any]) -> dict[str, Any]:
    inputs = example.get("inputs") or {}
    return {
        "messages": [{"role": "user", "content": inputs.get("user_message") or ""}],
        "raw_query": inputs.get("user_message") or "",
        "masked_content": inputs.get("user_message") or "",
        "normalized_query": inputs.get("user_message") or "",
        "category": inputs.get("category") or "faq",
        "routing_target": inputs.get("routing_target") or "faq_agent",
        "is_actionable": True,
        "user_id": inputs.get("user_id") or 1,
        "account_id": inputs.get("account_id"),
        "retry_count": 0,
        # Intentionally omit ticket_id so failed-query writes are skipped during eval.
    }


def retrieved_contexts(documents: list[dict[str, Any]]) -> list[str]:
    return [
        str(document.get("chunk_text") or document.get("content") or "")
        for document in documents
        if document.get("chunk_text") or document.get("content")
    ]


def source_hit_at_k(
    documents: list[dict[str, Any]],
    *,
    expected_documents: list[str],
    expected_chunks: list[str],
    acceptable_source_types: list[str],
    k: int,
) -> tuple[bool, dict[str, Any]]:
    top_docs = documents[:k]
    retrieved_document_ids = {str(row.get("document_id") or row.get("documents_id") or "") for row in top_docs}
    retrieved_chunk_ids = {str(row.get("chunk_id") or "") for row in top_docs}
    retrieved_source_types = {str(row.get("source_type") or "") for row in top_docs}
    expected_document_ids = {str(value) for value in expected_documents}
    expected_chunk_ids = {str(value) for value in expected_chunks}
    acceptable_source_type_set = {str(value) for value in acceptable_source_types}
    document_hit = bool(expected_document_ids & retrieved_document_ids) if expected_document_ids else False
    chunk_hit = bool(expected_chunk_ids & retrieved_chunk_ids) if expected_chunk_ids else False
    source_type_hit = (
        bool(acceptable_source_type_set & retrieved_source_types)
        if acceptable_source_type_set
        else False
    )
    return document_hit or chunk_hit or source_type_hit, {
        "retrieved_document_ids": sorted(value for value in retrieved_document_ids if value),
        "retrieved_chunk_ids": sorted(value for value in retrieved_chunk_ids if value),
        "retrieved_source_types": sorted(value for value in retrieved_source_types if value),
        "matched_documents": sorted(expected_document_ids & retrieved_document_ids),
        "matched_chunks": sorted(expected_chunk_ids & retrieved_chunk_ids),
        "matched_source_types": sorted(acceptable_source_type_set & retrieved_source_types),
    }


@lru_cache(maxsize=1)
def faithfulness_metric() -> Any:
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness

    model = os.environ.get("RAGAS_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    metric = Faithfulness()
    metric.llm = LangchainLLMWrapper(ChatOpenAI(model=model, api_key=api_key, temperature=0))
    return metric


async def faithfulness_score(question: str, answer: str, contexts: list[str]) -> float | str:
    if not contexts:
        return "no_retrieved_contexts"
    try:
        from ragas import SingleTurnSample
    except ImportError:
        return "ragas_not_installed"

    sample = SingleTurnSample(user_input=question, response=answer, retrieved_contexts=contexts)
    try:
        return float(await faithfulness_metric().single_turn_ascore(sample))
    except Exception as exc:
        return f"ragas_error:{type(exc).__name__}"


def record_ragas_faithfulness_estimate(question: str, answer: str, contexts: list[str]) -> None:
    model = os.environ.get("RAGAS_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    prompt_text = "\n\n".join([question, answer, *contexts])
    record_usage(
        component="ragas_faithfulness_estimated",
        model=model,
        prompt_tokens=estimate_tokens(prompt_text, model),
        completion_tokens=128,
        successful_requests=1,
        estimated=True,
    )


def infer_answerability(row: dict[str, Any]) -> str:
    explicit = row.get("answerability") or row.get("expected_answerability")
    if explicit in {"answerable", "unanswerable"}:
        return str(explicit)

    answer = str(row.get("answer") or "")
    if any(re.search(pattern, answer) for pattern in UNANSWERABLE_PATTERNS):
        return "unanswerable"
    return "answerable"


def is_fallback_correct(row: dict[str, Any]) -> bool:
    answer = str(row.get("answer") or "")
    return any(re.search(pattern, answer) for pattern in UNANSWERABLE_PATTERNS)


def _average_numeric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [
        float(row[key])
        for row in rows
        if isinstance(row.get(key), (int, float))
    ]
    return round(sum(values) / len(values), 4) if values else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {}
    source_hits = [bool(row["source_hit@5"]) for row in rows]
    false_fallbacks = [bool(row["false_fallback"]) for row in rows]
    latencies = [float(row["latency_ms"]) for row in rows]
    answerable_rows = [row for row in rows if row.get("answerability") == "answerable"]
    unanswerable_rows = [row for row in rows if row.get("answerability") == "unanswerable"]
    fallback_correct_rows = [
        row for row in unanswerable_rows if bool(row.get("fallback_correctness"))
    ]
    return {
        "total": total,
        "source_hit@5": round(sum(source_hits) / total, 4),
        "false_fallback_rate": round(sum(false_fallbacks) / total, 4),
        "avg_latency_ms": round(sum(latencies) / total, 2),
        "p95_latency_ms": round(sorted(latencies)[int(total * 0.95) - 1], 2) if total else None,
        "avg_faithfulness": _average_numeric(rows, "faithfulness"),
        "answerable_count": len(answerable_rows),
        "unanswerable_count": len(unanswerable_rows),
        "avg_faithfulness_answerable_only": _average_numeric(answerable_rows, "faithfulness"),
        "source_hit@5_answerable_only": round(
            sum(bool(row["source_hit@5"]) for row in answerable_rows) / len(answerable_rows),
            4,
        )
        if answerable_rows
        else None,
        "fallback_correctness_unanswerable": round(
            len(fallback_correct_rows) / len(unanswerable_rows),
            4,
        )
        if unanswerable_rows
        else None,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
        "successful_requests": sum(int(row.get("successful_requests") or 0) for row in rows),
        "total_cost_usd": round(sum(float(row.get("total_cost_usd") or 0.0) for row in rows), 8),
        "has_estimated_usage": any(bool(row.get("has_estimated_usage")) for row in rows),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    csv_path = path.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "question",
        "source_hit@5",
        "answerability",
        "fallback_correctness",
        "false_fallback",
        "faithfulness",
        "latency_ms",
        "faq_failure_reason",
        "retrieved_count",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "total_cost_usd",
        "has_estimated_usage",
        "usage_by_component",
        "expected_documents",
        "expected_chunks",
        "matched_documents",
        "matched_chunks",
        "matched_source_types",
        "answer",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row.get(key), ensure_ascii=False)
                    if isinstance(row.get(key), (list, dict))
                    else row.get(key)
                    for key in fieldnames
                }
            )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FAQ agent against a DB-grounded JSON dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--enable-ragas", action="store_true", help="Compute RAGAS faithfulness.")
    parser.add_argument(
        "--disable-retrieval-cache",
        action="store_true",
        help="Disable retrieval cache after .env loading so eval runs are comparable.",
    )
    parser.add_argument(
        "--reranker-enabled",
        choices=["true", "false"],
        help="Override RERANKER_ENABLED after .env loading.",
    )
    args = parser.parse_args()

    load_env()
    if args.disable_retrieval_cache:
        os.environ["FAQ_RETRIEVAL_CACHE_ENABLED"] = "false"
    if args.reranker_enabled is not None:
        os.environ["RERANKER_ENABLED"] = args.reranker_enabled
    dataset_info, examples = load_dataset(args.dataset)
    if args.limit is not None:
        examples = examples[: args.limit]

    rows: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        inputs = example.get("inputs") or {}
        outputs = example.get("outputs") or {}
        metadata = example.get("metadata") or {}
        started_at = time.perf_counter()
        try:
            with usage_tracking_context() as usage_tracker:
                result = run_faq_rag(make_state(example))
                documents = list(result.get("retrieved_documents") or [])
                answer = str(result.get("draft_text") or "")
                faithfulness: float | str | None = None
                if args.enable_ragas and answer:
                    contexts = retrieved_contexts(documents)
                    record_ragas_faithfulness_estimate(
                        str(inputs.get("user_message") or ""),
                        answer,
                        contexts,
                    )
                    faithfulness = await faithfulness_score(
                        str(inputs.get("user_message") or ""),
                        answer,
                        contexts,
                    )
                token_usage = summarize_usage(usage_tracker)
            error = None
        except Exception as exc:
            result = {
                "draft_text": "",
                "retrieved_documents": [],
                "retrieval_query": "",
                "faq_failure_reason": f"eval_error:{type(exc).__name__}",
            }
            documents = []
            answer = ""
            faithfulness = None
            token_usage = summarize_usage({})
            error = repr(exc)
        latency_ms = (time.perf_counter() - started_at) * 1000

        expected_documents = [
            str(value)
            for value in (outputs.get("acceptable_documents") or outputs.get("source_documents") or [])
        ]
        expected_chunks = [
            str(value)
            for value in (outputs.get("acceptable_chunks") or outputs.get("expected_chunks") or [])
        ]
        acceptable_source_types = [str(value) for value in outputs.get("acceptable_source_types") or []]
        hit, hit_details = source_hit_at_k(
            documents,
            expected_documents=expected_documents,
            expected_chunks=expected_chunks,
            acceptable_source_types=acceptable_source_types,
            k=5,
        )
        false_fallback = bool(answer.strip() == SAFE_FALLBACK_RESPONSE and (expected_documents or expected_chunks))

        row = {
            "test_id": metadata.get("test_id") or f"FAQ-{index:03d}",
            "question": inputs.get("user_message"),
            "source_hit@5": hit,
            "false_fallback": false_fallback,
            "faithfulness": faithfulness,
            "latency_ms": round(latency_ms, 2),
            "faq_failure_reason": result.get("faq_failure_reason"),
            "retrieved_count": len(documents),
            "total_tokens": token_usage.get("total_tokens"),
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "completion_tokens": token_usage.get("completion_tokens"),
            "successful_requests": token_usage.get("successful_requests"),
            "total_cost_usd": token_usage.get("total_cost_usd"),
            "has_estimated_usage": token_usage.get("has_estimated_usage"),
            "usage_by_component": token_usage.get("components"),
            "expected_documents": expected_documents,
            "expected_chunks": expected_chunks,
            "answer": answer,
            "error": error,
            **hit_details,
        }
        row["answerability"] = str(outputs.get("answerability") or infer_answerability(row))
        row["fallback_correctness"] = (
            is_fallback_correct(row) if row["answerability"] == "unanswerable" else None
        )
        rows.append(row)
        print(
            f"[{index}/{len(examples)}] {row['test_id']} "
            f"source_hit@5={row['source_hit@5']} false_fallback={row['false_fallback']} "
            f"latency_ms={row['latency_ms']} failure={row['faq_failure_reason']}"
        )

    report = {
        "dataset": dataset_info.get("dataset_info") or {},
        "summary": summarize(rows),
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_csv(args.output, rows)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    asyncio.run(main())
