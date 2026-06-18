from __future__ import annotations

import csv
from datetime import datetime
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[4]
EVAL_DIR = Path(__file__).resolve().parent
AGENT_NAME = "answer_agent"
DATASET_PATH = ROOT_DIR / "data" / "tests" / "answer_agents" / "answer_agent_eval_live_gold_20260618.json"
os.environ.setdefault("CS_AUTO_KEYWORD_DIR", str(ROOT_DIR / "data" / "keywords"))
os.environ.setdefault("CS_AUTO_SQL_DIR", str(ROOT_DIR / "data" / "sql"))

for path in reversed(
    [
        ROOT_DIR / "apps" / "cs_auto" / "backend",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents.tool.dbsearch import DbSearchRouter  # noqa: E402
from agents.tool.docsearch import DocumentRetriever  # noqa: E402
from common.db.connection import db_connection  # noqa: E402


DB_ROUTING_TARGETS = {"DB_only", "DB&DOC"}
DOC_ROUTING_TARGETS = {"doc_only", "DB&DOC"}
PROGRESS_EVERY = 5


def _load_root_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _require_live_env() -> None:
    required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "LLM_API_KEY", "LLM_MODEL"]
    missing = [key for key in required if not os.environ.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required env vars for live answer-agent eval: {', '.join(missing)}")


def _load_eval_examples() -> list[dict[str, Any]]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return list(payload.get("examples", []))


def _normalize_question(question: str) -> str:
    text = str(question or "").replace("\r\n", "\n").strip()
    if "AI:" in text:
        text = text.split("AI:", 1)[0].strip()
    if text.startswith("User:"):
        text = text.split("User:", 1)[1].strip()
    return text


def _title_from_question(question: str, max_chars: int = 60) -> str:
    normalized = " ".join(_normalize_question(question).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."


def _derive_category(example: dict[str, Any]) -> str:
    return str(example.get("category") or "general")


def _expected_query_type(example: dict[str, Any], category: str) -> str:
    if example.get("routing_target") not in DB_ROUTING_TARGETS:
        return ""
    return str(example.get("gold_query_type") or "fixed_sql")


def _build_ticket_payload(example: dict[str, Any], question: str) -> dict[str, object]:
    ticket = example.get("ticket", {})
    return {
        "ticket_id": int(example["ticket_id"]),
        "account_id": ticket.get("account_id"),
        "user_id": ticket.get("user_id"),
        "title": _title_from_question(question),
        "raw_query": question,
        "source_type": "eval_dataset",
        "status": "open",
        "session_id": None,
        "inquiry_created_at": ticket.get("created_at"),
    }


def _build_analysis_payload(example: dict[str, Any], question: str, category: str) -> dict[str, object]:
    ticket = example.get("ticket", {})
    return {
        "analysis_id": None,
        "category": category,
        "enriched_query": question,
        "routing_target": example["routing_target"],
        "summary": "live answer-agent eval case",
        "account_id": ticket.get("account_id"),
        "user_id": ticket.get("user_id"),
    }


def _stringify_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}"


def _extract_gold_documents(example: dict[str, Any]) -> list[dict[str, Any]]:
    documents = example.get("gold_documents") or []
    return [document for document in documents if isinstance(document, dict)]


def _verify_gold_documents_in_live_db(gold_documents: list[dict[str, Any]]) -> dict[str, Any]:
    if not gold_documents:
        return {
            "gold_doc_total": 0,
            "gold_doc_verified_count": 0,
            "gold_chunk_verified_count": 0,
            "all_document_ids_exist": True,
            "all_chunk_ids_exist": True,
            "missing_document_ids": [],
            "missing_chunk_ids": [],
        }

    document_ids = sorted({str(document.get("document_id") or "") for document in gold_documents if document.get("document_id")})
    chunk_ids = sorted({str(document.get("chunk_id") or "") for document in gold_documents if document.get("chunk_id")})

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT documents_id
                FROM documents
                WHERE documents_id = ANY(%s)
                """,
                (document_ids,),
            )
            existing_document_ids = {str(row["documents_id"]) for row in cur.fetchall()}
            cur.execute(
                """
                SELECT chunk_id
                FROM documents_chunks
                WHERE chunk_id = ANY(%s)
                """,
                (chunk_ids,),
            )
            existing_chunk_ids = {str(row["chunk_id"]) for row in cur.fetchall()}

    missing_document_ids = [document_id for document_id in document_ids if document_id not in existing_document_ids]
    missing_chunk_ids = [chunk_id for chunk_id in chunk_ids if chunk_id not in existing_chunk_ids]
    return {
        "gold_doc_total": len(gold_documents),
        "gold_doc_verified_count": len(existing_document_ids),
        "gold_chunk_verified_count": len(existing_chunk_ids),
        "all_document_ids_exist": not missing_document_ids,
        "all_chunk_ids_exist": not missing_chunk_ids,
        "missing_document_ids": missing_document_ids,
        "missing_chunk_ids": missing_chunk_ids,
    }


def _run_db_case(router: DbSearchRouter, ticket_payload: dict[str, object], analysis_payload: dict[str, object], expected_query_type: str) -> dict[str, Any]:
    router_decision: dict[str, Any] | None = None
    router_error = ""
    try:
        router_decision_model = router.decide_query_type(ticket_payload, analysis_payload)
        router_decision = router_decision_model.model_dump()
        actual_query_type = str(router_decision_model.query_type)
    except Exception as exc:
        router_error = _stringify_error(exc)
        actual_query_type = ""

    fixed_result: dict[str, Any]
    fixed_error = ""
    try:
        fixed_result = router.fixed_sql.run(ticket_payload, analysis_payload)
    except Exception as exc:
        fixed_error = _stringify_error(exc)
        fixed_result = {"sql": "", "rows": [], "evidence": [], "plan": None}

    text_result: dict[str, Any]
    text_error = ""
    try:
        text_result = router.text_to_sql.run(ticket_payload, analysis_payload)
    except Exception as exc:
        text_error = _stringify_error(exc)
        text_result = {"sql": "", "rows": [], "evidence": [], "plan": None}

    chosen_result = fixed_result if actual_query_type == "fixed_sql" else text_result if actual_query_type == "text_to_sql" else None
    chosen_error = fixed_error if actual_query_type == "fixed_sql" else text_error if actual_query_type == "text_to_sql" else router_error
    return {
        "expected_query_type": expected_query_type,
        "actual_query_type": actual_query_type,
        "router_match": actual_query_type == expected_query_type,
        "router_reason": "" if not router_decision else str(router_decision.get("reason") or ""),
        "router_error": router_error,
        "fixed_sql_ok": not fixed_error and bool(fixed_result.get("sql")),
        "fixed_sql_sql": str(fixed_result.get("sql") or ""),
        "fixed_sql_row_count": len(fixed_result.get("rows", [])),
        "fixed_sql_evidence_count": len(fixed_result.get("evidence", [])),
        "fixed_sql_error": fixed_error,
        "text_to_sql_ok": not text_error and bool(text_result.get("sql")),
        "text_to_sql_sql": str(text_result.get("sql") or ""),
        "text_to_sql_row_count": len(text_result.get("rows", [])),
        "text_to_sql_evidence_count": len(text_result.get("evidence", [])),
        "text_to_sql_error": text_error or str(text_result.get("error") or ""),
        "chosen_path_ok": bool(chosen_result and chosen_result.get("sql")) and not chosen_error,
        "chosen_path_row_count": 0 if chosen_result is None else len(chosen_result.get("rows", [])),
        "chosen_path_evidence_count": 0 if chosen_result is None else len(chosen_result.get("evidence", [])),
        "chosen_path_error": chosen_error,
    }


def _run_document_case(doc_retriever: DocumentRetriever, ticket_payload: dict[str, object], analysis_payload: dict[str, object], gold_documents: list[dict[str, Any]]) -> dict[str, Any]:
    validation = _verify_gold_documents_in_live_db(gold_documents)
    document_query = None
    retrieved_documents: list[dict[str, Any]] = []
    document_error = ""

    try:
        document_query = doc_retriever.query_builder.build(ticket_payload, analysis_payload)
        documents = doc_retriever.document_searcher.search(document_query)
        retrieved_documents = [document.model_dump() for document in documents]
    except Exception as exc:
        document_error = _stringify_error(exc)

    gold_chunk_ids = {str(document.get("chunk_id") or "") for document in gold_documents if document.get("chunk_id")}
    gold_document_ids = {str(document.get("document_id") or "") for document in gold_documents if document.get("document_id")}
    retrieved_chunk_ids = [str(document.get("chunk_id") or "") for document in retrieved_documents]
    retrieved_document_ids = [str(document.get("document_id") or "") for document in retrieved_documents]

    matched_gold_chunks = sorted(gold_chunk_ids & set(retrieved_chunk_ids))
    matched_gold_documents = sorted(gold_document_ids & set(retrieved_document_ids))
    return {
        "gold_doc_total": validation["gold_doc_total"],
        "gold_doc_verified_count": validation["gold_doc_verified_count"],
        "gold_chunk_verified_count": validation["gold_chunk_verified_count"],
        "all_gold_document_ids_exist": validation["all_document_ids_exist"],
        "all_gold_chunk_ids_exist": validation["all_chunk_ids_exist"],
        "missing_gold_document_ids": "|".join(validation["missing_document_ids"]),
        "missing_gold_chunk_ids": "|".join(validation["missing_chunk_ids"]),
        "document_eval_ok": not document_error and bool(document_query),
        "document_query_text": "" if document_query is None else str(document_query.query_text),
        "document_retrieval_query": "" if document_query is None else str(document_query.retrieval_query),
        "document_result_count": len(retrieved_documents),
        "document_gold_chunk_hit": bool(matched_gold_chunks),
        "document_gold_document_hit": bool(matched_gold_documents),
        "matched_gold_chunk_ids": "|".join(matched_gold_chunks),
        "matched_gold_document_ids": "|".join(matched_gold_documents),
        "document_error": document_error,
    }


def _run_case(router: DbSearchRouter, doc_retriever: DocumentRetriever, example: dict[str, Any]) -> dict[str, Any]:
    question = _normalize_question(str(example.get("ticket", {}).get("question") or ""))
    category = _derive_category(example)
    expected_query_type = _expected_query_type(example, category)
    ticket_payload = _build_ticket_payload(example, question)
    analysis_payload = _build_analysis_payload(example, question, category)

    result = {
        "ticket_id": ticket_payload["ticket_id"],
        "title": ticket_payload["title"],
        "routing_target": example["routing_target"],
        "category": category,
        "question": question,
        "expected_query_type": "",
        "actual_query_type": "",
        "router_match": "",
        "router_reason": "",
        "router_error": "",
        "fixed_sql_ok": "",
        "fixed_sql_row_count": "",
        "fixed_sql_evidence_count": "",
        "fixed_sql_error": "",
        "fixed_sql_sql": "",
        "text_to_sql_ok": "",
        "text_to_sql_row_count": "",
        "text_to_sql_evidence_count": "",
        "text_to_sql_error": "",
        "text_to_sql_sql": "",
        "chosen_path_ok": "",
        "chosen_path_row_count": "",
        "chosen_path_evidence_count": "",
        "chosen_path_error": "",
        "gold_doc_total": "",
        "gold_doc_verified_count": "",
        "gold_chunk_verified_count": "",
        "all_gold_document_ids_exist": "",
        "all_gold_chunk_ids_exist": "",
        "missing_gold_document_ids": "",
        "missing_gold_chunk_ids": "",
        "document_eval_ok": "",
        "document_query_text": "",
        "document_retrieval_query": "",
        "document_result_count": "",
        "document_gold_chunk_hit": "",
        "document_gold_document_hit": "",
        "matched_gold_chunk_ids": "",
        "matched_gold_document_ids": "",
        "document_error": "",
    }

    if example["routing_target"] in DB_ROUTING_TARGETS:
        result.update(_run_db_case(router, ticket_payload, analysis_payload, expected_query_type))

    if example["routing_target"] in DOC_ROUTING_TARGETS:
        gold_documents = _extract_gold_documents(example)
        result.update(_run_document_case(doc_retriever, ticket_payload, analysis_payload, gold_documents))

    return result


def _print_progress(index: int, total: int, case_result: dict[str, Any]) -> None:
    router_actual = case_result["actual_query_type"] or "-"
    doc_hit = case_result["document_gold_chunk_hit"] if case_result["document_gold_chunk_hit"] != "" else "-"
    print(
        (
            f"[{index}/{total}] ticket_id={case_result['ticket_id']} "
            f"routing={case_result['routing_target']} category={case_result['category']} "
            f"router={router_actual} doc_hit={doc_hit}"
        ),
        flush=True,
    )


def _build_report(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    db_cases = [case for case in case_results if case["routing_target"] in DB_ROUTING_TARGETS]
    doc_cases = [case for case in case_results if case["routing_target"] in DOC_ROUTING_TARGETS]

    expected_counts = Counter(str(case["expected_query_type"]) for case in db_cases if case["expected_query_type"] != "")
    actual_counts = Counter(str(case["actual_query_type"]) or "error" for case in db_cases)

    report = {
        "dataset_path": str(DATASET_PATH),
        "ticket_count": len(case_results),
        "db_case_count": len(db_cases),
        "doc_case_count": len(doc_cases),
        "generated_at": datetime.now().isoformat(),
        "metrics": {
            "router_decision": {
                "correct": sum(1 for case in db_cases if case["router_match"] is True),
                "total": len(db_cases),
                "accuracy": round(sum(1 for case in db_cases if case["router_match"] is True) / len(db_cases), 4) if db_cases else 0.0,
                "expected_counts": dict(expected_counts),
                "actual_counts": dict(actual_counts),
            },
            "fixed_sql": {
                "attempted": len(db_cases),
                "executed_ok": sum(1 for case in db_cases if case["fixed_sql_ok"] is True),
                "non_empty_rows": sum(1 for case in db_cases if int(case["fixed_sql_row_count"] or 0) > 0),
                "expected_cases": sum(1 for case in db_cases if case["expected_query_type"] == "fixed_sql"),
                "expected_cases_with_rows": sum(
                    1 for case in db_cases if case["expected_query_type"] == "fixed_sql" and int(case["fixed_sql_row_count"] or 0) > 0
                ),
            },
            "text_to_sql": {
                "attempted": len(db_cases),
                "executed_ok": sum(1 for case in db_cases if case["text_to_sql_ok"] is True),
                "non_empty_rows": sum(1 for case in db_cases if int(case["text_to_sql_row_count"] or 0) > 0),
                "expected_cases": sum(1 for case in db_cases if case["expected_query_type"] == "text_to_sql"),
                "expected_cases_with_rows": sum(
                    1 for case in db_cases if case["expected_query_type"] == "text_to_sql" and int(case["text_to_sql_row_count"] or 0) > 0
                ),
            },
            "chosen_path": {
                "attempted": len(db_cases),
                "executed_ok": sum(1 for case in db_cases if case["chosen_path_ok"] is True),
                "non_empty_rows": sum(1 for case in db_cases if int(case["chosen_path_row_count"] or 0) > 0),
                "router_match_and_non_empty_rows": sum(
                    1 for case in db_cases if case["router_match"] is True and int(case["chosen_path_row_count"] or 0) > 0
                ),
            },
            "document_retrieval": {
                "attempted": len(doc_cases),
                "executed_ok": sum(1 for case in doc_cases if case["document_eval_ok"] is True),
                "non_empty_results": sum(1 for case in doc_cases if int(case["document_result_count"] or 0) > 0),
                "gold_chunk_hit_cases": sum(1 for case in doc_cases if case["document_gold_chunk_hit"] is True),
                "gold_document_hit_cases": sum(1 for case in doc_cases if case["document_gold_document_hit"] is True),
            },
            "dataset_live_db_verification": {
                "doc_cases": len(doc_cases),
                "all_gold_document_ids_exist_cases": sum(1 for case in doc_cases if case["all_gold_document_ids_exist"] is True),
                "all_gold_chunk_ids_exist_cases": sum(1 for case in doc_cases if case["all_gold_chunk_ids_exist"] is True),
                "gold_documents_total": sum(int(case["gold_doc_total"] or 0) for case in doc_cases),
                "gold_document_ids_verified_total": sum(int(case["gold_doc_verified_count"] or 0) for case in doc_cases),
                "gold_chunk_ids_verified_total": sum(int(case["gold_chunk_verified_count"] or 0) for case in doc_cases),
            },
        },
        "errors": [
            {
                "ticket_id": case["ticket_id"],
                "title": case["title"],
                "router_error": case["router_error"],
                "fixed_sql_error": case["fixed_sql_error"],
                "text_to_sql_error": case["text_to_sql_error"],
                "chosen_path_error": case["chosen_path_error"],
                "document_error": case["document_error"],
                "missing_gold_document_ids": case["missing_gold_document_ids"],
                "missing_gold_chunk_ids": case["missing_gold_chunk_ids"],
            }
            for case in case_results
            if any(
                [
                    case["router_error"],
                    case["fixed_sql_error"],
                    case["text_to_sql_error"],
                    case["chosen_path_error"],
                    case["document_error"],
                    case["missing_gold_document_ids"],
                    case["missing_gold_chunk_ids"],
                ]
            )
        ],
        "cases": case_results,
    }
    return report


def _build_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = EVAL_DIR / timestamp / AGENT_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _save_artifacts(report: dict[str, Any], output_dir: Path) -> None:
    metric_rows = []
    for section, metrics in report["metrics"].items():
        row = {"section": section}
        row.update(metrics)
        metric_rows.append(row)

    _write_csv(
        output_dir / "summary.csv",
        metric_rows,
        [
            "section",
            "correct",
            "total",
            "accuracy",
            "attempted",
            "executed_ok",
            "non_empty_rows",
            "non_empty_results",
            "expected_cases",
            "expected_cases_with_rows",
            "router_match_and_non_empty_rows",
            "gold_chunk_hit_cases",
            "gold_document_hit_cases",
            "doc_cases",
            "all_gold_document_ids_exist_cases",
            "all_gold_chunk_ids_exist_cases",
            "gold_documents_total",
            "gold_document_ids_verified_total",
            "gold_chunk_ids_verified_total",
            "expected_counts",
            "actual_counts",
        ],
    )

    case_fieldnames = [
        "ticket_id",
        "title",
        "routing_target",
        "category",
        "expected_query_type",
        "actual_query_type",
        "router_match",
        "router_reason",
        "router_error",
        "fixed_sql_ok",
        "fixed_sql_row_count",
        "fixed_sql_evidence_count",
        "fixed_sql_error",
        "text_to_sql_ok",
        "text_to_sql_row_count",
        "text_to_sql_evidence_count",
        "text_to_sql_error",
        "chosen_path_ok",
        "chosen_path_row_count",
        "chosen_path_evidence_count",
        "chosen_path_error",
        "gold_doc_total",
        "gold_doc_verified_count",
        "gold_chunk_verified_count",
        "all_gold_document_ids_exist",
        "all_gold_chunk_ids_exist",
        "missing_gold_document_ids",
        "missing_gold_chunk_ids",
        "document_eval_ok",
        "document_query_text",
        "document_retrieval_query",
        "document_result_count",
        "document_gold_chunk_hit",
        "document_gold_document_hit",
        "matched_gold_chunk_ids",
        "matched_gold_document_ids",
        "document_error",
        "question",
        "fixed_sql_sql",
        "text_to_sql_sql",
    ]
    _write_csv(output_dir / "case_results.csv", report["cases"], case_fieldnames)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_report(report: dict[str, Any], output_dir: Path | None = None) -> None:
    print("\n[answer_agent evaluation]")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    if report["errors"]:
        print("\n[errors]")
        print(json.dumps(report["errors"], ensure_ascii=False, indent=2))
    if output_dir is not None:
        print(f"\n[artifacts]\n{output_dir}")


def _evaluate_dataset(*, show_progress: bool = False) -> dict[str, Any]:
    router = DbSearchRouter()
    doc_retriever = DocumentRetriever()
    examples = _load_eval_examples()
    case_results: list[dict[str, Any]] = []

    total = len(examples)
    for index, example in enumerate(examples, start=1):
        case_result = _run_case(router, doc_retriever, example)
        case_results.append(case_result)
        if show_progress and (index == 1 or index % PROGRESS_EVERY == 0 or index == total):
            _print_progress(index, total, case_result)

    return _build_report(case_results)


def test_answer_agent_eval_on_live_candidate_set() -> None:
    r"""Run live answer-agent evaluation and save CSV/JSON artifacts.

    실행:
    `python -m pytest apps\tests\cs-auto_tests\eval\test_answer_agent_eval.py -s`

    필요 환경:
    - `CS_AUTO_RUN_LIVE_EVAL=1`
    - `.env` 또는 환경변수에 `DB_*`, `LLM_API_KEY`, `LLM_MODEL`
    """

    if os.environ.get("CS_AUTO_RUN_LIVE_EVAL") != "1":
        pytest.skip("Set CS_AUTO_RUN_LIVE_EVAL=1 to run the live answer-agent evaluation.")

    _load_root_env()
    try:
        _require_live_env()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    report = _evaluate_dataset()
    output_dir = _build_output_dir()
    _save_artifacts(report, output_dir)
    _print_report(report, output_dir)

    assert report["ticket_count"] > 0
    assert report["metrics"]["dataset_live_db_verification"]["doc_cases"] > 0


if __name__ == "__main__":
    _load_root_env()
    _require_live_env()
    print(f"[start] dataset={DATASET_PATH}", flush=True)
    report = _evaluate_dataset(show_progress=True)
    output_dir = _build_output_dir()
    _save_artifacts(report, output_dir)
    _print_report(report, output_dir)
    print("[done] evaluation finished", flush=True)
