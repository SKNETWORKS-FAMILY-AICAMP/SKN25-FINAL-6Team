from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.chains.faq_rag import format_contexts, retrieve_faq_context


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _save_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


MetricSuite = Literal["rag", "agent", "all"]


def build_eval_rows(input_path: Path, *, top_k: int, limit: int | None = None) -> list[dict[str, Any]]:
    """Load FAQ eval rows and fill missing retrieved_contexts via the project RAG chain."""
    rows = _load_jsonl(input_path)
    if limit is not None:
        rows = rows[:limit]
    enriched = []
    for row in rows:
        question = row.get("user_input") or row.get("question")
        if not question:
            raise ValueError("Each eval row needs user_input or question.")

        contexts = row.get("retrieved_contexts")
        if not contexts:
            rag_context = retrieve_faq_context(question, top_k=top_k)
            row["retrieval_query"] = rag_context.retrieval_query
            row["retrieved_documents"] = rag_context.documents
            row["retrieval_trace"] = rag_context.retrieval_trace
            contexts = format_contexts(rag_context.documents)
        if not contexts:
            contexts = ["NO_RETRIEVED_CONTEXT"]

        enriched.append(
            {
                "user_input": question,
                "response": row.get("response") or row.get("answer") or "",
                "reference": row.get("reference") or row.get("ground_truth") or "",
                "retrieved_contexts": contexts,
                "retrieval_query": row.get("retrieval_query"),
                "retrieved_documents": row.get("retrieved_documents") or [],
                "retrieval_trace": row.get("retrieval_trace") or [],
                "reference_topics": row.get("reference_topics") or ["game_cs", "faq", "policy"],
                "reference_tool_calls": row.get("reference_tool_calls") or [],
                "actual_tool_calls": row.get("actual_tool_calls") or [],
                "agent_reference": row.get("agent_reference") or row.get("reference") or "",
            }
        )
    return enriched


def _rag_metrics() -> list[Any]:
    """Load RAGAS single-turn metrics with current and legacy import fallbacks."""
    try:
        from ragas.metrics.collections import (
            FactualCorrectness,
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            NoiseSensitivity,
            ResponseRelevancy,
        )
    except ImportError as exc:
        try:
            from ragas.metrics import (
                FactualCorrectness,
                Faithfulness,
                LLMContextPrecisionWithReference,
                LLMContextRecall,
                NoiseSensitivity,
                ResponseRelevancy,
            )
        except ImportError:
            raise exc

    return [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
        NoiseSensitivity(),
        FactualCorrectness(),
    ]


def _ragas_judges() -> dict[str, Any]:
    """Build explicit RAGAS judge LLM/embedding wrappers to avoid default API mismatch."""
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

    judges: dict[str, Any] = {}
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
    except ImportError:
        return judges

    judges["llm"] = LangchainLLMWrapper(
        ChatOpenAI(model=llm_model, api_key=api_key, temperature=0)
    )
    judges["embeddings"] = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=embedding_model, api_key=api_key)
    )
    return judges


def _agent_metrics() -> list[Any]:
    """Load RAGAS multi-turn agent/tool metrics."""
    try:
        from ragas.metrics.collections import (
            AgentGoalAccuracyWithReference,
            ToolCallAccuracy,
            TopicAdherenceScore,
        )
    except ImportError as exc:
        try:
            from ragas.metrics import (
                AgentGoalAccuracyWithReference,
                ToolCallAccuracy,
                TopicAdherenceScore,
            )
        except ImportError:
            raise exc

    return [
        ToolCallAccuracy(),
        AgentGoalAccuracyWithReference(),
        TopicAdherenceScore(),
    ]


def run_rag_ragas(rows: list[dict[str, Any]]) -> Any:
    """Run six single-turn RAGAS metrics for FAQ/RAG answer quality."""
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS is not installed. Install eval dependencies first: "
            "pip install -r requirements-ragas.txt"
        ) from exc

    samples = [
        SingleTurnSample(
            user_input=row["user_input"],
            response=row["response"],
            reference=row["reference"],
            retrieved_contexts=row["retrieved_contexts"],
        )
        for row in rows
    ]
    dataset = EvaluationDataset(samples=samples)
    return evaluate(dataset=dataset, metrics=_rag_metrics(), **_ragas_judges())


def _to_tool_call(raw: dict[str, Any]) -> Any:
    from ragas.messages import ToolCall

    return ToolCall(
        name=raw.get("name") or raw.get("tool_name"),
        args=raw.get("args") or raw.get("arguments") or {},
    )


def run_agent_ragas(rows: list[dict[str, Any]]) -> Any | None:
    """Run three multi-turn RAGAS agent metrics when tool trace fields are present."""
    try:
        from ragas import EvaluationDataset, MultiTurnSample, evaluate
        from ragas.messages import AIMessage, HumanMessage
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS is not installed. Install eval dependencies first: "
            "pip install -r requirements-ragas.txt"
        ) from exc

    trace_rows = [
        row for row in rows
        if row.get("actual_tool_calls") or row.get("reference_tool_calls")
    ]
    if not trace_rows:
        print(
            "Skipped agent metrics: rows need actual_tool_calls/reference_tool_calls "
            "to evaluate Tool Call Accuracy, Agent Goal Accuracy, and Topic Adherence."
        )
        return None

    samples = []
    for row in trace_rows:
        actual_tool_calls = [_to_tool_call(call) for call in row.get("actual_tool_calls", [])]
        reference_tool_calls = [_to_tool_call(call) for call in row.get("reference_tool_calls", [])]
        samples.append(
            MultiTurnSample(
                user_input=[
                    HumanMessage(content=row["user_input"]),
                    AIMessage(content=row["response"], tool_calls=actual_tool_calls),
                ],
                reference=row.get("agent_reference") or row.get("reference") or "",
                reference_tool_calls=reference_tool_calls,
                reference_topics=row.get("reference_topics") or ["game_cs", "faq", "policy"],
            )
        )

    dataset = EvaluationDataset(samples=samples)
    return evaluate(dataset=dataset, metrics=_agent_metrics(), **_ragas_judges())


def run_ragas(rows: list[dict[str, Any]], *, metric_suite: MetricSuite) -> dict[str, Any]:
    """Run the requested RAGAS metric suites."""
    results: dict[str, Any] = {}
    if metric_suite in {"rag", "all"}:
        results["rag"] = run_rag_ragas(rows)
    if metric_suite in {"agent", "all"}:
        agent_result = run_agent_ragas(rows)
        if agent_result is not None:
            results["agent"] = agent_result
    return results


def _save_result_tables(results: dict[str, Any], output_path: Path) -> None:
    for suite_name, result in results.items():
        print(f"\n[{suite_name}]")
        print(result)
        if hasattr(result, "to_pandas"):
            csv_path = output_path.with_name(f"{output_path.stem}_{suite_name}.csv")
            result.to_pandas().to_csv(csv_path, index=False)
            print(f"Saved {suite_name} RAGAS result table to {csv_path}")


def print_metric_plan() -> None:
    print(
        """
Metric suites:
- RAG single-turn: Faithfulness, Answer/Response Relevancy, Context Precision, Context Recall, Noise Sensitivity, Factual Correctness.
- Agent multi-turn: Tool Call Accuracy, Agent Goal Accuracy, Topic Adherence.

Agent metrics require JSONL rows with actual_tool_calls/reference_tool_calls. Example:
{"actual_tool_calls":[{"name":"refine_retrieval_query","args":{"text":"..."}}],"reference_tool_calls":[{"name":"refine_retrieval_query","args":{"text":"..."}}],"reference_topics":["game_cs","faq","policy"]}
""".strip()
    )


def _validate_metric_inputs(rows: list[dict[str, Any]], *, metric_suite: MetricSuite) -> None:
    if metric_suite in {"rag", "all"}:
        empty_responses = [row["user_input"] for row in rows if not row.get("response")]
        if empty_responses:
            preview = "\n".join(f"- {question}" for question in empty_responses[:3])
            raise ValueError(
                f"{len(empty_responses)} rows have empty response. "
                "RAGAS answer metrics require chatbot responses.\n"
                "First generate/fill the response field for each row, or run only context-building "
                "with --skip-ragas.\n"
                f"Examples:\n{preview}"
            )

        empty_references = [row["user_input"] for row in rows if not row.get("reference")]
        if empty_references:
            preview = "\n".join(f"- {question}" for question in empty_references[:3])
            raise ValueError(
                f"{len(empty_references)} rows have empty reference. "
                "Context Recall, Noise Sensitivity, and Factual Correctness need references.\n"
                f"Examples:\n{preview}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FAQ/RAG answers with RAGAS.")
    parser.add_argument("--input", help="JSONL with question/answer/reference rows.")
    parser.add_argument("--output", default="evals/experiments/faq_ragas_rows.jsonl")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, help="Evaluate only the first N rows.")
    parser.add_argument(
        "--metric-suite",
        choices=["rag", "agent", "all"],
        default="all",
        help="rag=6 answer/retrieval metrics, agent=3 tool/goal/topic metrics, all=both.",
    )
    parser.add_argument("--list-metrics", action="store_true", help="Print supported metric groups.")
    parser.add_argument("--skip-ragas", action="store_true", help="Only build contexts; do not run RAGAS.")
    args = parser.parse_args()

    if args.list_metrics:
        print_metric_plan()
        return

    if not args.input:
        parser.error("--input is required unless --list-metrics is used.")

    load_dotenv(override=True)
    rows = build_eval_rows(Path(args.input), top_k=args.top_k, limit=args.limit)
    output_path = Path(args.output)
    _save_jsonl(output_path, rows)

    if args.skip_ragas:
        print(f"Saved enriched eval rows to {args.output}")
        return

    _validate_metric_inputs(rows, metric_suite=args.metric_suite)
    results = run_ragas(rows, metric_suite=args.metric_suite)
    _save_result_tables(results, output_path)


if __name__ == "__main__":
    main()
