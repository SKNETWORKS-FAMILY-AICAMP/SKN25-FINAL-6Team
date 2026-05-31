from __future__ import annotations

import json

from chatbot.chains import persistence


def _base_state() -> dict:
    return {
        "ticket_id": 1,
        "analysis_id": 2,
        "draft_text": "draft answer",
        "reasoning_node": "faq_agent",
        "category": "FAQ",
        "routing_target": "rag_reply",
    }


def test_draft_persistence_saves_retrieved_documents_as_evidence(monkeypatch) -> None:
    evidence_payloads = []

    monkeypatch.setattr(persistence, "_write_answer_draft", lambda payload: json.dumps({"draft_id": 10}))
    monkeypatch.setattr(persistence, "_write_evidence_doc", lambda payload: evidence_payloads.append(payload) or "{}")

    state = {
        **_base_state(),
        "retrieved_documents": [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "source_type": "hoyoverse_qna_common",
                "chunk_text": "first evidence",
                "score": 0.05,
            },
            {
                "chunk_id": "chunk-2",
                "document_id": "doc-2",
                "source_type": "naver_cafe_notice",
                "chunk_text": "second evidence",
                "score": 0.03,
            },
        ],
    }

    result = persistence.draft_persistence_node(state)

    assert result == {"draft_id": 10, "evidence_count": 2}
    assert evidence_payloads[0]["source_id"] == "chunk-1"
    assert evidence_payloads[0]["source_type"] == "hoyoverse_qna_common"
    assert evidence_payloads[0]["evidence_text"] == "first evidence"
    assert evidence_payloads[0]["retrieval_rank"] == 1
    assert evidence_payloads[1]["source_id"] == "chunk-2"


def test_draft_persistence_falls_back_to_draft_evidence(monkeypatch) -> None:
    evidence_payloads = []

    monkeypatch.setattr(persistence, "_write_answer_draft", lambda payload: json.dumps({"draft_id": 11}))
    monkeypatch.setattr(persistence, "_write_evidence_doc", lambda payload: evidence_payloads.append(payload) or "{}")

    result = persistence.draft_persistence_node(_base_state())

    assert result == {"draft_id": 11, "evidence_count": 1}
    assert evidence_payloads == [
        {
            "draft_id": 11,
            "source_type": "agent",
            "source_id": "faq_agent_generated_draft",
            "evidence_text": "draft answer",
            "relevance_score": 1.0,
            "retrieval_rank": 1,
        }
    ]
