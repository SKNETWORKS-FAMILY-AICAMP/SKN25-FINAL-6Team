from __future__ import annotations

import csv
from datetime import datetime
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest


ROOT_DIR = Path(__file__).resolve().parents[4]
EVAL_DIR = Path(__file__).resolve().parent
AGENT_NAME = "analysis_agent"
DATASET_PATH = ROOT_DIR / "data" / "tests" / "analysis_agents" / "analysis_eval_all_axes_10_each_20260616.csv"
os.environ.setdefault("CS_AUTO_KEYWORD_DIR", str(ROOT_DIR / "data" / "keywords"))

for path in reversed(
    [
        ROOT_DIR / "apps" / "cs_auto" / "backend",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents import analysis_agent as agent  # noqa: E402


LABEL_FIELDS = (
    "category",
    "risk_level",
    "sentiment",
    "routing_target",
)

GOLD_TO_PRED = {
    "gold_category": "category",
    "gold_risk_level": "risk_level",
    "gold_sentiment": "sentiment",
    "gold_routing_target": "routing_target",
}


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


def _load_eval_tickets() -> list[dict[str, str]]:
    rows = list(csv.DictReader(DATASET_PATH.open(encoding="utf-8-sig")))
    deduped: dict[str, dict[str, str]] = {}
    for row in rows:
        deduped.setdefault(row["ticket_id"], row)
    return list(deduped.values())


def _ticket_payload(row: dict[str, str]) -> dict[str, object]:
    return {
        "ticket_id": int(row["ticket_id"]),
        "title": row["title"],
        "raw_query": row["raw_query"].replace(" / ", "\n"),
        "source_type": row["source_type"],
        "status": "open",
        "account_id": None,
        "user_id": None,
        "session_id": None,
    }


def _evaluate_dataset() -> dict[str, Any]:
    tickets = _load_eval_tickets()
    report: dict[str, Any] = {
        "dataset_path": str(DATASET_PATH),
        "ticket_count": len(tickets),
        "metrics": {},
        "confusion_matrices": {},
        "errors": [],
        "mismatches": [],
    }

    counts = {field: {"correct": 0, "total": 0} for field in LABEL_FIELDS}
    confusion: dict[str, dict[str, Counter[str]]] = {
        field: defaultdict(Counter) for field in LABEL_FIELDS
    }

    for row in tickets:
        payload = _ticket_payload(row)
        try:
            result = agent.build_analysis_result(payload).model_dump()
        except Exception as exc:
            report["errors"].append(
                {
                    "ticket_id": row["ticket_id"],
                    "title": row["title"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        mismatch_row = {
            "ticket_id": row["ticket_id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "gold_category": row["gold_category"],
            "pred_category": str(result["category"]),
            "gold_risk_level": row["gold_risk_level"],
            "pred_risk_level": str(result["risk_level"]),
            "gold_sentiment": row["gold_sentiment"],
            "pred_sentiment": str(result["sentiment"]),
            "gold_routing_target": row["gold_routing_target"],
            "pred_routing_target": "" if result["routing_target"] is None else str(result["routing_target"]),
            "raw_query": row["raw_query"],
            "mismatch_fields": "",
        }
        mismatch_fields: list[str] = []
        for gold_field, pred_field in GOLD_TO_PRED.items():
            gold = row[gold_field]
            pred = result[pred_field]
            pred_value = "" if pred is None else str(pred)
            counts[pred_field]["total"] += 1
            if pred_value == gold:
                counts[pred_field]["correct"] += 1
            else:
                mismatch_fields.append(pred_field)
            confusion[pred_field][gold][pred_value] += 1
        if mismatch_fields:
            mismatch_row["mismatch_fields"] = ",".join(mismatch_fields)
            report["mismatches"].append(mismatch_row)

    for field in LABEL_FIELDS:
        total = counts[field]["total"]
        correct = counts[field]["correct"]
        accuracy = correct / total if total else 0.0
        report["metrics"][field] = {
            "correct": correct,
            "total": total,
            "accuracy": round(accuracy, 4),
        }
        report["confusion_matrices"][field] = {
            gold: dict(pred_counts)
            for gold, pred_counts in sorted(confusion[field].items())
        }

    return report


def _format_confusion_matrix_markdown(report: dict[str, Any]) -> str:
    sections: list[str] = ["# Analysis Agent Confusion Matrix", ""]
    for field, matrix in report["confusion_matrices"].items():
        label_names = sorted(
            {
                *matrix.keys(),
                *(pred for pred_counts in matrix.values() for pred in pred_counts.keys()),
            }
        )
        sections.append(f"## {field}")
        if not label_names:
            sections.append("")
            sections.append("No data")
            sections.append("")
            continue

        header = "| gold \u2193 / pred \u2192 | " + " | ".join(label_names) + " |"
        separator = "|---|" + "|".join("---" for _ in label_names) + "|"
        sections.append(header)
        sections.append(separator)
        for gold in label_names:
            pred_counts = matrix.get(gold, {})
            row = [str(pred_counts.get(pred, 0)) for pred in label_names]
            sections.append("| " + gold + " | " + " | ".join(row) + " |")
        sections.append("")
    return "\n".join(sections)


def _print_report(report: dict[str, Any], output_dir: Path | None = None) -> None:
    print("\n[analysis_agent evaluation]")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))

    print("\n[presentation confusion matrix]")
    print(_format_confusion_matrix_markdown(report))

    if report["errors"]:
        print("\n[errors]")
        print(json.dumps(report["errors"], ensure_ascii=False, indent=2))

    if output_dir is not None:
        print(f"\n[artifacts]\n{output_dir}")


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
    accuracy_rows = []
    for axis, metric in report["metrics"].items():
        accuracy_rows.append(
            {
                "axis": axis,
                "correct": metric["correct"],
                "total": metric["total"],
                "accuracy": metric["accuracy"],
            }
        )
    _write_csv(
        output_dir / "accuracy_summary.csv",
        accuracy_rows,
        ["axis", "correct", "total", "accuracy"],
    )

    mismatch_fieldnames = [
        "ticket_id",
        "title",
        "source_type",
        "gold_category",
        "pred_category",
        "gold_risk_level",
        "pred_risk_level",
        "gold_sentiment",
        "pred_sentiment",
        "gold_routing_target",
        "pred_routing_target",
        "mismatch_fields",
        "raw_query",
    ]
    _write_csv(output_dir / "mismatches.csv", report["mismatches"], mismatch_fieldnames)

    confusion_markdown = _format_confusion_matrix_markdown(report)
    (output_dir / "confusion_matrix.md").write_text(confusion_markdown, encoding="utf-8")
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def test_analysis_agent_accuracy_on_manual_gold_set() -> None:
    r"""수동 라벨링한 정답셋에 대해 analysis_agent 정확도를 계산한다.

    실행 예:
    `python -m pytest apps\tests\cs-auto_tests\test_analysis_agent_eval.py -s`

    실제 LLM 호출이 포함되므로 기본값은 skip 이고, 아래 환경 변수가 있어야 실행된다.
    - `CS_AUTO_RUN_LIVE_EVAL=1`
    - `.env` 또는 환경변수에 `LLM_API_KEY`, `LLM_MODEL`
    """

    if os.environ.get("CS_AUTO_RUN_LIVE_EVAL") != "1":
        pytest.skip("Set CS_AUTO_RUN_LIVE_EVAL=1 to run the live analysis-agent evaluation.")

    _load_root_env()
    if not os.environ.get("LLM_API_KEY") or not os.environ.get("LLM_MODEL"):
        pytest.skip("LLM_API_KEY and LLM_MODEL are required for live evaluation.")

    report = _evaluate_dataset()
    output_dir = _build_output_dir()
    _save_artifacts(report, output_dir)
    _print_report(report, output_dir)

    assert report["ticket_count"] > 0
    for field in LABEL_FIELDS:
        assert report["metrics"][field]["total"] > 0


if __name__ == "__main__":
    _load_root_env()
    report = _evaluate_dataset()
    output_dir = _build_output_dir()
    _save_artifacts(report, output_dir)
    _print_report(report, output_dir)
