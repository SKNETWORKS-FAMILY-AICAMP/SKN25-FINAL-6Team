from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
os.environ.setdefault("CS_AUTO_SQL_DIR", str(ROOT_DIR / "data" / "sql"))

for path in reversed(
    [
        ROOT_DIR,
        ROOT_DIR / "apps" / "cs_auto" / "backend",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents.tool import docsearch  # noqa: E402
from common.retrieval.vector_tools import RetrievalQuery, _query_overlap_ratio, _rule_source_types  # noqa: E402


def test_query_overlap_ratio_detects_unrelated_enrichment() -> None:
    assert _query_overlap_ratio("가장 최근에 나온 공지가 어떤거야?", "계정 비밀번호 변경 방법") == 0.0
    assert _query_overlap_ratio("비밀번호 변경 방법", "계정 비밀번호 변경 방법") > 0.5


def test_document_query_builder_falls_back_when_enrichment_drifts(monkeypatch) -> None:
    monkeypatch.setattr(
        docsearch,
        "enrich_retrieval_query",
        lambda text: RetrievalQuery(
            query_text="계정 비밀번호 변경 방법",
            preferred_source_types=["universe_qna_onlydaily"],
            preferred_categories=["계정 관리"],
        ),
    )
    monkeypatch.setattr(
        docsearch,
        "refine_retrieval_query",
        type("Refiner", (), {"invoke": staticmethod(lambda payload: "가장 최근에 나온 공지가 어떤거야")}),
    )

    query = docsearch.DocumentQueryBuilder().build(
        {"ticket_id": 615039168},
        {"category": "policy", "enriched_query": "가장 최근에 나온 공지가 어떤거야?"},
    )

    assert query.retrieval_query == "가장 최근에 나온 공지가 어떤거야"


def test_rule_source_types_include_live_universe_sources() -> None:
    source_types = _rule_source_types("비밀번호는 어떻게 변경하나요?")

    assert "universe_qna_onlydaily" in source_types
    assert "universe_qna_common" in source_types
    assert "universe_policy" in source_types
