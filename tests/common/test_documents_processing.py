from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.common.documents_processing.chunking import chunk_document, estimate_token_count
from src.common.documents_processing.normalize import normalize_document_text
from src.common.documents_processing.pipeline import run_documents_pipeline
from src.common.documents_processing.types import DocumentRecord, EmbeddingRecord


class FakeRepository:
    def __init__(self, documents: list[DocumentRecord]) -> None:
        self.documents = documents
        self.saved: list[tuple[str, int, int]] = []

    def load_documents(self, **kwargs) -> list[DocumentRecord]:
        _ = kwargs
        return self.documents

    def rebuild_document_artifacts(self, *, document_id, chunks, embeddings) -> None:
        self.saved.append((document_id, len(chunks), len(embeddings)))


class FakeEmbedder:
    model_name = "fake-embedding-model"

    def embed_chunks(self, chunks):
        return [
            EmbeddingRecord(
                embedding_id=f"{chunk.chunk_id}::embedding",
                chunk_id=chunk.chunk_id,
                embedding_vector=[0.1, 0.2, 0.3],
                embedding_model=self.model_name,
                source_type=chunk.source_type,
                category=chunk.category,
            )
            for chunk in chunks
        ]


def make_document(raw_content: str, *, document_id: str = "doc-1", title: str = "결제 안내") -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        source_type="policy",
        category="payment",
        title=title,
        raw_content=raw_content,
        source_url=None,
        published_at=None,
        updated_at=None,
    )


def test_normalize_document_text_preserves_korean_and_symbols() -> None:
    raw = "\ufeff결제\u200b 안내\r\n\r\n### 환불/취소 : 7일 이내\t요청 가능\x00\n----\n문의 URL: https://example.com/help?id=10"
    normalized = normalize_document_text(raw)

    assert "결제 안내" in normalized
    assert "환불/취소 : 7일 이내 요청 가능" in normalized
    assert "https://example.com/help?id=10" in normalized
    assert "\u200b" not in normalized
    assert "\x00" not in normalized
    assert "----" not in normalized


def test_chunk_document_generates_deterministic_chunks() -> None:
    raw = (
        "# 결제 FAQ\n\n"
        "결제가 완료되지 않으면 결제 수단과 네트워크 상태를 먼저 확인해 주세요. "
        "결제 승인 지연은 최대 10분까지 발생할 수 있습니다.\n\n"
        "## 환불 안내\n\n"
        "환불은 결제일 기준 7일 이내에 요청할 수 있으며 사용 이력이 있는 상품은 제한될 수 있습니다. "
        "문의 시 주문번호와 결제 시간을 함께 전달해 주세요.\n\n"
        "## 추가 확인\n\n"
        "스토어 영수증, 인앱 결제 내역, 계정 식별자를 함께 보내면 처리 속도가 빨라집니다."
    )
    document = make_document(raw)

    chunks = chunk_document(document, normalize_document_text(raw), max_tokens=35, overlap_tokens=8, min_tokens=10)

    assert len(chunks) >= 2
    assert [chunk.chunk_order for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].chunk_id == "doc-1::chunk::0"
    assert all(chunk.chunk_text.startswith("결제 안내") for chunk in chunks)
    assert all(chunk.token_count == estimate_token_count(chunk.chunk_text) for chunk in chunks)


def test_run_documents_pipeline_processes_and_skips_documents() -> None:
    documents = [
        make_document("결제 오류가 발생하면 주문번호를 확인하고 고객센터로 접수해 주세요.\n\n환불은 7일 이내 요청 가능합니다."),
        make_document(" \n\r\t ", document_id="doc-2", title="빈 문서"),
    ]
    repository = FakeRepository(documents)

    result = run_documents_pipeline(repository=repository, embedder=FakeEmbedder(), dry_run=False)

    assert result.total_documents == 2
    assert result.processed_documents == 1
    assert result.skipped_documents == 1
    assert result.failed_documents == 0
    assert result.total_chunks >= 1
    assert result.total_embeddings == result.total_chunks
    assert repository.saved[0][0] == "doc-1"
