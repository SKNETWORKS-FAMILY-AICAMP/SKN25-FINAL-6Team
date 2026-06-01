from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.service.chatbot_service import run_chatbot


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _tool_calls_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort extraction of LangChain tool calls from final state messages."""
    tool_calls: list[dict[str, Any]] = []
    for message in state.get("messages", []):
        raw_calls = []
        if isinstance(message, dict):
            raw_calls = message.get("tool_calls") or []
        else:
            raw_calls = getattr(message, "tool_calls", []) or []

        for call in raw_calls:
            if isinstance(call, dict):
                tool_calls.append(
                    {
                        "name": call.get("name"),
                        "args": call.get("args") or call.get("arguments") or {},
                    }
                )
            else:
                tool_calls.append(
                    {
                        "name": getattr(call, "name", None),
                        "args": getattr(call, "args", {}) or {},
                    }
                )
    return [call for call in tool_calls if call.get("name")]


def _retrieval_trace_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    documents = state.get("retrieved_documents") or []
    trace = []
    if state.get("retrieval_enrichment"):
        trace.append({"step": "enrich_retrieval_query", "output": state["retrieval_enrichment"]})
    if state.get("retrieval_query"):
        trace.append({"step": "embed_query", "input": state["retrieval_query"]})
    if documents:
        trace.append(
            {
                "step": "search_document_chunks",
                "result_count": len(documents),
                "candidate_scope": documents[0].get("candidate_scope"),
            }
        )
        trace.append({"step": "rerank_documents", "result_count": len(documents)})
    if state.get("faq_failure_reason"):
        trace.append({"step": "faq_failure", "reason": state["faq_failure_reason"]})
    return trace


def generate_responses(
    rows: list[dict[str, Any]],
    *,
    limit: int | None,
    start_ticket_id: int,
    output_path: Path,
) -> list[dict[str, Any]]:
    target_rows = rows[:limit] if limit is not None else rows
    completed: list[dict[str, Any]] = []

    for index, row in enumerate(target_rows, start=1):
        question = row.get("user_input") or row.get("question")
        if not question:
            raise ValueError(f"Row {index} is missing user_input/question.")

        if row.get("response"):
            completed.append(row)
            _write_jsonl(output_path, completed)
            continue

        ticket_id = start_ticket_id + index - 1
        print(f"[{index}/{len(target_rows)}] generating response for ticket_id={ticket_id}")
        output = run_chatbot(
            ticket_id=ticket_id,
            user_message=question,
            account_id=None,
            user_id=1,
            session_id=9000 + index,
            source_type="ragas_eval",
        )

        state = output.get("state", {})
        enriched = dict(row)
        enriched["response"] = output.get("answer") or ""
        enriched["actual_tool_calls"] = _tool_calls_from_state(state)
        enriched["retrieval_query"] = state.get("retrieval_query") or row.get("retrieval_query")
        enriched["retrieval_enrichment"] = state.get("retrieval_enrichment") or row.get("retrieval_enrichment")
        enriched["retrieved_documents"] = state.get("retrieved_documents") or row.get("retrieved_documents") or []
        enriched["retrieval_trace"] = _retrieval_trace_from_state(state) or row.get("retrieval_trace") or []
        enriched["faq_failure_reason"] = state.get("faq_failure_reason")
        enriched["generated_state_summary"] = {
            "category": state.get("category"),
            "routing_target": state.get("routing_target"),
            "reasoning_node": state.get("reasoning_node"),
            "safety_action": state.get("safety_action"),
        }
        completed.append(enriched)
        _write_jsonl(output_path, completed)

    if limit is not None and len(rows) > limit:
        completed.extend(rows[limit:])
        _write_jsonl(output_path, completed)

    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chatbot responses for FAQ/RAGAS eval rows.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, help="Generate only the first N rows.")
    parser.add_argument("--start-ticket-id", type=int, default=100000)
    args = parser.parse_args()

    load_dotenv(override=True)
    rows = _load_jsonl(Path(args.input))
    output_path = Path(args.output)
    generate_responses(
        rows,
        limit=args.limit,
        start_ticket_id=args.start_ticket_id,
        output_path=output_path,
    )
    print(f"Saved responses to {output_path}")


if __name__ == "__main__":
    main()
