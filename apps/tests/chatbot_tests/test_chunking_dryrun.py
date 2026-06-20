from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CHATBOT_DB_EXPLORATION_TESTS") != "true",
    reason="manual DB exploration test; set RUN_CHATBOT_DB_EXPLORATION_TESTS=true to run",
)


def test_documents_pipeline_dryrun() -> None:
    load_dotenv(".env", override=True)

    from common.documents_processing.pipeline import run_documents_pipeline

    for source_type in [
        "hoyoverse_qna_common",
        "hoyoverse_qna_onlygenshin",
        "hoyoverse_policy",
        "naver_cafe_notice",
        "naver_cafe_guide",
    ]:
        result = run_documents_pipeline(source_type=source_type, dry_run=True)
        assert result.total_documents >= 0
        assert result.total_chunks >= 0
