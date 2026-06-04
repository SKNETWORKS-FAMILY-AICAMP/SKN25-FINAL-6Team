from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[3]
for path in (
    ROOT_DIR / "apps" / "cs_auto" / "backend",
    ROOT_DIR / "packages" / "common-python" / "src",
):
    sys.path.insert(0, str(path))

from batch.airflow_jobs import run_naver_cafe_draft_batch, run_ticket_analysis_batch  # noqa: E402


BatchFn = Callable[..., dict[str, Any]]


def _print_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _run_job(
    *,
    name: str,
    fn: BatchFn,
    target_date: str | None,
    limit: int,
    fail_fast: bool,
) -> bool:
    try:
        payload = fn(target_date=target_date, limit=limit, run_label="manual")
        _print_payload(payload)
        return True
    except Exception as exc:
        print(f"[{name}] failed: {exc}", file=sys.stderr)
        if fail_fast:
            raise
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cs_auto Airflow batch jobs manually.")
    parser.add_argument(
        "job",
        choices=("analysis", "naver-cafe-draft", "visible-drafts", "all"),
        help="Batch job to run.",
    )
    parser.add_argument("--target-date", default=None, help="Target date in YYYY-MM-DD format.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of candidate tickets.")
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="When job=all, continue to the next job after a failure.",
    )
    args = parser.parse_args()

    fail_fast = not args.no_fail_fast
    jobs: list[tuple[str, BatchFn]] = []
    if args.job in ("analysis", "all"):
        jobs.append(("analysis", run_ticket_analysis_batch))
    if args.job in ("naver-cafe-draft", "visible-drafts", "all"):
        jobs.append(("naver-cafe-draft", run_naver_cafe_draft_batch))

    ok = True
    for name, fn in jobs:
        ok = _run_job(
            name=name,
            fn=fn,
            target_date=args.target_date,
            limit=args.limit,
            fail_fast=fail_fast,
        ) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
