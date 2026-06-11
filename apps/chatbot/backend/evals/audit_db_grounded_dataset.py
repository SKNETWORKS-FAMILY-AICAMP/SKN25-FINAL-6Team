from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection


DATASET_DIR = Path(__file__).parent / "datasets"
DEFAULT_INPUT = DATASET_DIR / "gameops-chatbot-golden-v3.json"
DEFAULT_REPORT = DATASET_DIR / "gameops-chatbot-golden-v3-db-grounding-report.json"
DEFAULT_CANDIDATES = DATASET_DIR / "gameops-chatbot-golden-db-grounded-candidates.json"

DOCUMENT_EVIDENCE_SOURCE_TYPES = {
    "faq_document": {"hoyoverse_qna_common", "hoyoverse_qna_onlygenshin"},
    "policy_document": {"hoyoverse_policy"},
    "notice_document": {"naver_cafe_notice"},
    "game_guide": {"naver_cafe_guide"},
}

STRUCTURED_EVIDENCE_TABLES = {
    "payments": "payments",
    "refunds": "refunds",
    "item_delivery_logs": "item_delivery_logs",
    "gacha_logs": "gacha_logs",
}

REFERENCE_UNSUPPORTED_MARKERS = (
    "문서에서 확인되지",
    "단정하지",
    "문서 근거가 필요",
    "확인되는 삭제 절차",
    "확인되는",
    "근거가 없",
)

STOPWORDS = {
    "합니다",
    "해야",
    "한다",
    "안내",
    "근거",
    "문서",
    "확인",
    "경우",
    "여부",
    "관련",
    "사용자",
    "질문",
    "답변",
    "제공",
    "필요",
    "가능",
    "불가",
    "현재",
}


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[0-9A-Za-z가-힣_]+", text)
    cleaned = []
    for token in tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        cleaned.append(token)
    return list(dict.fromkeys(cleaned))


def reference_looks_unsupported(reference: str) -> bool:
    return any(marker in reference for marker in REFERENCE_UNSUPPORTED_MARKERS)


def evidence_types(example: dict[str, Any]) -> list[str]:
    outputs = example.get("outputs") or {}
    values = outputs.get("required_evidence_types") or []
    return [str(value) for value in values]


def document_hits(
    *,
    conn: Any,
    source_types: set[str],
    user_message: str,
    reference_answer: str,
    limit: int,
) -> list[dict[str, Any]]:
    tokens = tokenize(f"{user_message} {reference_answer}")[:18]
    if not tokens:
        return []

    source_placeholders = ", ".join(["%s"] * len(source_types))
    source_params = list(source_types)
    clauses = []
    params: list[Any] = []
    for token in tokens:
        pattern = f"%{token}%"
        clauses.extend(
            [
                "d.title ILIKE %s",
                "d.category ILIKE %s",
                "c.chunk_text ILIKE %s",
            ]
        )
        params.extend([pattern, pattern, pattern])

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT
                d.documents_id,
                d.source_type,
                d.category,
                d.title,
                c.chunk_id,
                c.chunk_text
            FROM documents d
            JOIN documents_chunks c ON c.document_id = d.documents_id
            WHERE d.source_type IN ({source_placeholders})
              AND ({' OR '.join(clauses)})
            ORDER BY d.documents_id, c.chunk_order
            LIMIT %s
            """,
            (*source_params, *params, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]

    ranked = []
    for row in rows:
        text = f"{row.get('title') or ''} {row.get('category') or ''} {row.get('chunk_text') or ''}"
        matched = [token for token in tokens if token in text]
        item = dict(row)
        item["matched_terms"] = matched
        item["matched_term_count"] = len(matched)
        item["snippet"] = " ".join(str(row.get("chunk_text") or "").split())[:500]
        item.pop("chunk_text", None)
        ranked.append(item)
    ranked.sort(key=lambda item: item["matched_term_count"], reverse=True)
    return ranked[:limit]


def structured_counts(conn: Any, user_id: int, account_id: int | None) -> dict[str, int]:
    account_filter = "AND (%s IS NULL OR a.account_id = %s)"
    account_params = (account_id, account_id)
    queries = {
        "payments": f"""
            SELECT COUNT(*)
            FROM payments p
            JOIN game_accounts a ON a.account_id = p.account_id
            WHERE a.user_id = %s {account_filter}
        """,
        "refunds": f"""
            SELECT COUNT(*)
            FROM refunds r
            JOIN payments p ON p.payment_id = r.payment_id
            JOIN game_accounts a ON a.account_id = p.account_id
            WHERE a.user_id = %s {account_filter}
        """,
        "item_delivery_logs": f"""
            SELECT COUNT(*)
            FROM item_delivery_logs d
            JOIN game_accounts a ON a.account_id = d.account_id
            WHERE a.user_id = %s {account_filter}
        """,
        "gacha_logs": f"""
            SELECT COUNT(*)
            FROM gacha_logs g
            JOIN game_accounts a ON a.account_id = g.account_id
            WHERE a.user_id = %s {account_filter}
        """,
    }
    with conn.cursor() as cur:
        counts = {}
        for name, query in queries.items():
            cur.execute(query, (user_id, *account_params))
            counts[name] = int(cur.fetchone()[0])
    return counts


def audit_example(conn: Any, example: dict[str, Any], *, evidence_limit: int) -> dict[str, Any]:
    inputs = example.get("inputs") or {}
    outputs = example.get("outputs") or {}
    metadata = example.get("metadata") or {}
    user_message = str(inputs.get("user_message") or "")
    reference_answer = str(outputs.get("reference_answer") or "")
    required = evidence_types(example)
    category = str(inputs.get("category") or "")

    issues: list[str] = []
    evidence: dict[str, Any] = {}

    if category in {"bug", "voc"}:
        issues.append("category_not_db_answer_grounded")

    if reference_looks_unsupported(reference_answer):
        issues.append("reference_is_missing_evidence_or_uncertainty_rubric")

    for evidence_type in required:
        source_types = DOCUMENT_EVIDENCE_SOURCE_TYPES.get(evidence_type)
        if source_types:
            hits = document_hits(
                conn=conn,
                source_types=source_types,
                user_message=user_message,
                reference_answer=reference_answer,
                limit=evidence_limit,
            )
            evidence[evidence_type] = hits
            if not hits:
                issues.append(f"missing_document_evidence:{evidence_type}")
            elif max(hit["matched_term_count"] for hit in hits) < 2:
                issues.append(f"weak_document_evidence:{evidence_type}")

    structured_required = [item for item in required if item in STRUCTURED_EVIDENCE_TABLES]
    if structured_required:
        user_id = int(inputs.get("user_id") or 0)
        account_id = inputs.get("account_id")
        account_id = int(account_id) if account_id is not None else None
        counts = structured_counts(conn, user_id, account_id)
        evidence["structured_counts"] = counts
        for evidence_type in structured_required:
            if counts.get(evidence_type, 0) <= 0:
                issues.append(f"missing_structured_evidence:{evidence_type}")

    unknown_required = [
        item
        for item in required
        if item not in DOCUMENT_EVIDENCE_SOURCE_TYPES and item not in STRUCTURED_EVIDENCE_TABLES
    ]
    for evidence_type in unknown_required:
        if evidence_type not in {"bug_report_context", "redis_retrieval_cache"}:
            issues.append(f"unknown_evidence_type:{evidence_type}")

    status = "pass" if not issues else "fail"
    return {
        "test_id": metadata.get("test_id"),
        "category": category,
        "user_message": user_message,
        "required_evidence_types": required,
        "status": status,
        "issues": issues,
        "evidence": evidence,
    }


def write_candidates(
    *,
    source_payload: dict[str, Any],
    examples: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    output_path: Path,
) -> None:
    passing_ids = {audit["test_id"] for audit in audits if audit["status"] == "pass"}
    candidates = [
        example
        for example in examples
        if (example.get("metadata") or {}).get("test_id") in passing_ids
    ]
    dataset_info = dict(source_payload.get("dataset_info") or {})
    dataset_info.update(
        {
            "name": "gameops-chatbot-golden-db-grounded-candidates",
            "description": "Candidate golden examples filtered by actual local DB/document grounding audit.",
            "source_dataset": dataset_info.get("name"),
            "total_examples": len(candidates),
            "filter_note": (
                "Automatically filtered. Review evidence snippets in the audit report before treating this as final golden data."
            ),
            "category_counts": dict(Counter(example["inputs"].get("category") for example in candidates)),
        }
    )
    output_path.write_text(
        json.dumps({"dataset_info": dataset_info, "examples": candidates}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a chatbot golden dataset against the current local DB.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--evidence-limit", type=int, default=3)
    args = parser.parse_args()

    source_payload, examples = load_dataset(args.input)
    with db_connection() as conn:
        audits = [audit_example(conn, example, evidence_limit=args.evidence_limit) for example in examples]
    summary = {
        "input": str(args.input),
        "total": len(audits),
        "status_counts": dict(Counter(audit["status"] for audit in audits)),
        "category_counts": dict(Counter(audit["category"] for audit in audits)),
        "issue_counts": dict(Counter(issue for audit in audits for issue in audit["issues"])),
    }
    args.report.write_text(
        json.dumps({"summary": summary, "items": audits}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_candidates(source_payload=source_payload, examples=examples, audits=audits, output_path=args.candidates)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report={args.report}")
    print(f"candidates={args.candidates}")


if __name__ == "__main__":
    main()
