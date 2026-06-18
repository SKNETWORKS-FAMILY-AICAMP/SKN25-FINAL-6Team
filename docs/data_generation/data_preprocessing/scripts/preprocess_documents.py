from __future__ import annotations

import importlib
from pathlib import Path


def main() -> None:
    # 1단계: 원천 문서 CSV를 고객센터 RAG에 맞게 정리한다.
    # - HTML/공백/게시판 잡음 제거
    # - 일상이 말투성 인트로 제거
    # - 성우 공개 카테고리 제거
    # - raw_content가 비어 있는 문서 제거
    make_documents = importlib.import_module("make_ihy_documents_csv")
    make_documents.main()

    # 2단계: 정리된 원본 문서를 검색 단위 chunk CSV로 나눈다.
    # - FAQ는 질문 1개 + 답변 1개 구조 유지
    # - 정책 문서는 조항 단위 우선 분리
    # - 공지/가이드는 소제목과 문단 길이를 기준으로 분리
    # - 중복 chunk 제거
    chunk_documents = importlib.import_module("chunk_documents_csv")
    chunk_documents.main()

    # 3단계: 팀에서 유지하기로 한 기존 chunk CSV도 동일한 명칭/URL 정규화 규칙을 적용한다.
    # 이 파일은 위 chunk 생성 산출물이 아니므로 별도 후처리가 필요하다.
    script_dir = Path(__file__).resolve().parent
    is_bundle_script = script_dir.name == "scripts" and script_dir.parent.name == "sj_data_preprocessing"
    if is_bundle_script:
        legacy_chunk_path = script_dir.parent / "processed_data" / "test_documents_chunks_202606151549.csv"
    else:
        legacy_chunk_path = (
            script_dir.parents[1]
            / "ihy_data-20260615T004221Z-3-001"
            / "ihy_data"
            / "test_documents_chunks_202606151549.csv"
        )
    make_documents.normalize_existing_csv(legacy_chunk_path)


if __name__ == "__main__":
    main()
