from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[4]


def _measure(
    name: str,
    fn: Callable[[], str],
    *,
    threshold_ms: int,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        detail = fn()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "system": name,
            "ok": True,
            "latency_ms": latency_ms,
            "threshold_ms": threshold_ms,
            "pass": latency_ms <= threshold_ms,
            "detail": detail,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "system": name,
            "ok": False,
            "latency_ms": latency_ms,
            "threshold_ms": threshold_ms,
            "pass": False,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


def _check_postgres() -> str:
    import psycopg

    conn = psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSLMODE", "disable"),
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
            assert row and row[0] == 1
        return "SELECT 1 ok"
    finally:
        conn.close()


def _check_redis() -> str:
    import redis

    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL not set")
    client = redis.Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    key = "healthcheck:external_integration"
    client.setex(key, 60, "ok")
    value = client.get(key)
    assert value == b"ok"
    return "SETEX/GET ok"


def _check_openai() -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o"
    client = OpenAI(api_key=api_key, timeout=10)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=5,
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    assert content.strip()
    return "chat completion ok"


def _check_slack() -> str:
    from slack_sdk import WebClient

    token = os.getenv("SLACK_BOT_TOKEN") or os.getenv("DASHBOARD_SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK token not set")
    result = WebClient(token=token, timeout=5).auth_test()
    assert result.get("ok")
    return "auth_test ok"


def _check_github() -> str:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN or GITHUB_REPOSITORY not set")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "gameops-integration-check",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert 200 <= response.status < 300
    return "repo metadata ok"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate single-call external integration latency.")
    parser.add_argument("--threshold-ms", type=int, default=5000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "outputs" / "external_integrations_eval.json"),
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")

    checks: list[tuple[str, Callable[[], str]]] = [
        ("PostgreSQL", _check_postgres),
        ("Redis", _check_redis),
        ("OpenAI API", _check_openai),
        ("Slack API", _check_slack),
        ("GitHub API", _check_github),
    ]
    raw_results: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for name, fn in checks:
        attempts = [
            _measure(name, fn, threshold_ms=args.threshold_ms)
            for _ in range(max(1, args.runs))
        ]
        raw_results.extend(attempts)
        latencies = [float(row["latency_ms"]) for row in attempts]
        ok_count = sum(1 for row in attempts if row["ok"])
        pass_count = sum(1 for row in attempts if row["pass"])
        sorted_latencies = sorted(latencies)
        p95_index = min(len(sorted_latencies) - 1, max(0, int(len(sorted_latencies) * 0.95) - 1))
        results.append(
            {
                "system": name,
                "runs": len(attempts),
                "ok_count": ok_count,
                "pass_count": pass_count,
                "avg_latency_ms": round(statistics.mean(latencies), 2),
                "p95_latency_ms": sorted_latencies[p95_index],
                "max_latency_ms": max(latencies),
                "threshold_ms": args.threshold_ms,
                "pass": pass_count == len(attempts),
                "attempts": attempts,
            }
        )
    summary = {
        "total": len(results),
        "passed": sum(1 for row in results if row["pass"]),
        "failed": sum(1 for row in results if not row["pass"]),
        "all_pass": all(row["pass"] for row in results),
        "runs_per_system": max(1, args.runs),
        "avg_latency_ms": round(sum(float(row["avg_latency_ms"]) for row in results) / len(results), 2),
        "max_latency_ms": max(float(row["max_latency_ms"]) for row in results),
        "threshold_ms": args.threshold_ms,
        "results": results,
        "raw_results": raw_results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
