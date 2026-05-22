from __future__ import annotations

import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


@dataclass
class TestResult:
    nodeid: str
    outcome: str
    message: str = ""


class _ReportPlugin:
    def __init__(self) -> None:
        self.results: dict[str, TestResult] = {}
        self.collection_errors: list[str] = []

    def pytest_runtest_logreport(self, report) -> None:
        if report.when != "call":
            return
        message = ""
        if report.failed:
            message = str(report.longrepr).splitlines()[-1]
        self.results[report.nodeid] = TestResult(
            nodeid=report.nodeid,
            outcome=report.outcome,
            message=message,
        )

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.collection_errors.append(str(report.longrepr))


SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "라우팅",
        [
            (
                "tests/chatbot/test_orchestrator_routing.py::test_galaxy_payment_how_to_routes_to_faq_without_account",
                "갤럭시 결제 방법 안내 -> FAQ/RAG",
            ),
            (
                "tests/chatbot/test_orchestrator_routing.py::test_galaxy_missing_paid_item_routes_to_payment",
                "갤럭시 결제 미지급 -> 결제/운영 확인",
            ),
            (
                "tests/chatbot/test_orchestrator_routing.py::test_payment_question_with_account_routes_to_payment",
                "계정 기반 결제 질문 -> 결제/운영 확인",
            ),
            (
                "tests/chatbot/test_orchestrator_routing.py::test_classify_uses_rule_before_llm",
                "명확한 결제 라우팅은 LLM 호출 전에 규칙으로 처리",
            ),
            (
                "tests/chatbot/test_orchestrator_routing.py::test_route_by_normalized_categories",
                "정상화된 카테고리명을 올바른 agent로 라우팅",
            ),
        ],
    ),
    (
        "검색",
        [
            (
                "tests/chatbot/test_hybrid_retrieval.py::test_refine_query_text_deduplicates_terms",
                "검색어 공백 정리와 중복 제거",
            ),
            (
                "tests/chatbot/test_hybrid_retrieval.py::test_hybrid_rank_documents_combines_bm25_and_cosine",
                "BM25 + cosine 점수를 함께 사용",
            ),
            (
                "tests/chatbot/test_hybrid_retrieval.py::test_search_document_chunks_prefers_faq_then_falls_back",
                "FAQ 문서 우선 검색 후 결과 없으면 전체 문서 fallback",
            ),
        ],
    ),
    (
        "답변 생성",
        [
            (
                "tests/chatbot/test_faq_agent_rag.py::test_run_faq_rag_blocks_llm_when_no_documents",
                "검색 결과 0개면 LLM 호출 안 함",
            ),
            (
                "tests/chatbot/test_faq_agent_rag.py::test_run_faq_rag_generates_once_with_evidence",
                "근거 문서가 있을 때만 답변 생성 LLM 1회 호출",
            ),
        ],
    ),
    (
        "근거 저장",
        [
            (
                "tests/chatbot/test_persistence_evidence.py::test_draft_persistence_saves_retrieved_documents_as_evidence",
                "retrieved_documents를 evidence_docs로 저장",
            ),
            (
                "tests/chatbot/test_persistence_evidence.py::test_draft_persistence_falls_back_to_draft_evidence",
                "근거 문서 없으면 fallback evidence 저장",
            ),
        ],
    ),
]


def _normalize_nodeid(nodeid: str) -> str:
    return nodeid.replace("\\", "/")


def _run_pytest() -> tuple[int, _ReportPlugin, str]:
    import pytest

    plugin = _ReportPlugin()
    output = StringIO()
    args = [
        "tests/chatbot",
        "--tb=short",
        "--disable-warnings",
        "-q",
    ]
    with redirect_stdout(output), redirect_stderr(output):
        exit_code = pytest.main(args, plugins=[plugin])
    return exit_code, plugin, output.getvalue()


def _print_result(result: TestResult | None, label: str) -> bool:
    if result is None:
        print(f"MISS {label} - 테스트를 찾지 못했습니다")
        return False
    if result.outcome == "passed":
        print(f"PASS {label}")
        return True
    if result.outcome == "skipped":
        print(f"SKIP {label}")
        return True
    print(f"FAIL {label} - {result.message or result.outcome}")
    return False


def main() -> None:
    exit_code, plugin, raw_output = _run_pytest()
    results = {_normalize_nodeid(nodeid): result for nodeid, result in plugin.results.items()}

    print("tests/chatbot 품질 체크 결과")
    success = exit_code == 0 and not plugin.collection_errors

    for section, checks in SECTIONS:
        print(f"\n[{section}]")
        for nodeid, label in checks:
            result = results.get(nodeid)
            success = _print_result(result, label) and success

    mapped = {nodeid for _, checks in SECTIONS for nodeid, _ in checks}
    extra_results = sorted(nodeid for nodeid in results if nodeid not in mapped)
    if extra_results:
        print("\n[기타 tests/chatbot]")
        for nodeid in extra_results:
            result = results[nodeid]
            label = nodeid.split("::")[-1]
            success = _print_result(result, label) and success

    if plugin.collection_errors:
        print("\n[수집 오류]")
        for error in plugin.collection_errors:
            print(f"FAIL 테스트 수집 실패 - {error.splitlines()[-1]}")

    if not success and raw_output.strip():
        print("\n[pytest 원본 출력]")
        print(raw_output.strip())

    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
