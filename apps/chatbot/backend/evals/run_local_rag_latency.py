from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = PROJECT_ROOT.parents[2] / "packages" / "common-python" / "src"
DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "gameops-chatbot-regression-v2.json"

for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.service.chatbot_service import stream_chatbot


def _load_env_without_tracing() -> None:
    load_dotenv(REPO_ROOT / ".env", override=False)
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["CHATBOT_LANGSMITH_TRACING"] = "false"


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("examples"), list):
        return data["examples"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported dataset shape: {path}")


def _rag_examples(path: Path, limit: int | None) -> list[dict[str, Any]]:
    examples = [
        example
        for example in _load_dataset(path)
        if (example.get("metadata") or {}).get("test_type") in {"rag", "ragas"}
    ]
    return examples[:limit] if limit is not None else examples


def _run_example(example: dict[str, Any]) -> dict[str, Any]:
    from chatbot.generation import faq_agent

    inputs = example["inputs"]
    metadata = example.get("metadata") or {}
    cache_events: list[dict[str, Any]] = []
    stage_timings: dict[str, float] = {}
    original_log_event = faq_agent.log_event
    original_enrich_retrieval_query = faq_agent.enrich_retrieval_query
    original_embed_query = faq_agent._embed_query
    original_search_document_chunks = faq_agent.search_document_chunks
    original_rerank_documents = faq_agent._rerank_documents
    original_generate_evidence_answer = faq_agent._generate_evidence_answer
    original_retry_retrieval_with_rewrite = faq_agent._retry_retrieval_with_rewrite

    def timed(name: str, func: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started_at = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                stage_timings[name] = stage_timings.get(name, 0.0) + (
                    (time.perf_counter() - started_at) * 1000
                )

        return wrapper

    def capture_log_event(event_type: str, **kwargs: Any) -> Any:
        if kwargs.get("tool_name") == "faq_retrieval_cache":
            cache_events.append(dict(kwargs.get("metadata") or {}))
        return original_log_event(event_type, **kwargs)

    faq_agent.log_event = capture_log_event
    faq_agent.enrich_retrieval_query = timed("enrich_retrieval_query", original_enrich_retrieval_query)
    faq_agent._embed_query = timed("embed_query", original_embed_query)
    faq_agent.search_document_chunks = timed("search_document_chunks", original_search_document_chunks)
    faq_agent._rerank_documents = timed("rerank_documents", original_rerank_documents)
    faq_agent._generate_evidence_answer = timed(
        "generate_evidence_answer",
        original_generate_evidence_answer,
    )
    faq_agent._retry_retrieval_with_rewrite = timed(
        "retry_retrieval_with_rewrite",
        original_retry_retrieval_with_rewrite,
    )
    try:
        started_at = time.perf_counter()
        result = stream_chatbot(
            ticket_id=int(inputs.get("ticket_id") or 900_000_000 + len(str(inputs.get("user_message") or ""))),
            user_message=str(inputs["user_message"]),
            category=inputs.get("category"),
            user_id=int(inputs.get("user_id") or 1),
            account_id=int(inputs.get("account_id") or 0),
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
    finally:
        faq_agent.log_event = original_log_event
        faq_agent.enrich_retrieval_query = original_enrich_retrieval_query
        faq_agent._embed_query = original_embed_query
        faq_agent.search_document_chunks = original_search_document_chunks
        faq_agent._rerank_documents = original_rerank_documents
        faq_agent._generate_evidence_answer = original_generate_evidence_answer
        faq_agent._retry_retrieval_with_rewrite = original_retry_retrieval_with_rewrite

    state = result.get("state") or {}
    cache_hit = any(event.get("cache_hit") for event in cache_events)
    cache_backend = next((event.get("cache_backend") for event in cache_events if event.get("cache_backend")), None)
    cache_key_hash = next((event.get("cache_key_hash") for event in cache_events if event.get("cache_key_hash")), None)
    return {
        "test_id": metadata.get("test_id"),
        "question": inputs.get("user_message"),
        "route": state.get("reasoning_node"),
        "safety_action": state.get("safety_action"),
        "retrieval_query": state.get("retrieval_query"),
        "latency_ms": latency_ms,
        "cache_hit": cache_hit,
        "cache_backend": cache_backend,
        "cache_key_hash": cache_key_hash,
        "cache_events": cache_events,
        "stage_timings_ms": stage_timings,
        "retrieved_document_count": len(state.get("retrieved_documents") or []),
        "answer": result.get("answer"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local RAG-only latency checks without LangSmith/RAGAS.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("local-results/hy-rag-latency.json"))
    args = parser.parse_args()

    _load_env_without_tracing()
    examples = _rag_examples(args.input, args.limit)
    results = []
    for index, example in enumerate(examples, start=1):
        test_id = (example.get("metadata") or {}).get("test_id") or index
        print(f"[{index}/{len(examples)}] running {test_id}")
        result = _run_example(example)
        results.append(result)
        latency = result.get("latency_ms")
        latency_text = round(float(latency), 1) if latency is not None else "unknown"
        print(
            f"  latency_ms={latency_text} route={result.get('route')} "
            f"cache_hit={result.get('cache_hit')} backend={result.get('cache_backend')}"
        )
        timings = result.get("stage_timings_ms") or {}
        if timings:
            timing_summary = ", ".join(
                f"{name}={round(ms / 1000, 2)}s"
                for name, ms in sorted(timings.items(), key=lambda item: item[1], reverse=True)
            )
            print(f"  stages: {timing_summary}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} local RAG latency results to {args.output}")


if __name__ == "__main__":
    main()
