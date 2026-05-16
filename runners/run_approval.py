from __future__ import annotations

import json
import re

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from data.seed_payload import build_first_input_payload, clone_payload
from operation.approvalagent.chain import (
    approval_core_chain,
    final_outcome_chain,
    mark_answer_draft_approved,
)


def _first(value: object) -> dict:
    return value[0] if isinstance(value, list) else value


def _tokenize(text: str) -> list[str]:
    # 한글/영문/숫자 단위로 잘라 간단한 검색 토큰으로 사용한다.
    return re.findall(r"[0-9A-Za-z가-힣_]+", text.lower())


def _build_query_text(state: dict) -> str:
    ticket = _first(state["qa_ticket"])
    analysis = _first(state["ticket_analysis"])
    payments = state["operation_logs"].get("payments", [])
    refunds = state["operation_logs"].get("refunds", [])
    deliveries = state["operation_logs"].get("item_delivery_logs", [])
    parts = [
        str(ticket.get("title", "")),
        str(ticket.get("raw_content", "")),
        str(analysis.get("category", "")),
        str(analysis.get("summary", "")),
    ]
    parts.extend(str(row.get("payment_status", "")) for row in payments)
    parts.extend(str(row.get("refund_status", "")) for row in refunds)
    parts.extend(str(row.get("delivery_status", "")) for row in deliveries)
    return " ".join(part for part in parts if part)


def _score_chunk(chunk: dict, document: dict, query_tokens: set[str], category: str) -> float:
    chunk_tokens = set(_tokenize(str(chunk.get("chunk_text", ""))))
    doc_tokens = set(_tokenize(str(document.get("title", "")))) | set(_tokenize(str(document.get("raw_content", ""))))
    overlap_score = float(len(query_tokens & (chunk_tokens | doc_tokens)))
    category_bonus = 5.0 if str(document.get("category", "")).lower() == category.lower() else 0.0
    source_bonus_map = {"POLICY": 1.5, "FAQ": 1.0, "NOTICE": 0.5}
    source_bonus = source_bonus_map.get(str(document.get("source_type", "")).upper(), 0.0)
    return overlap_score + category_bonus + source_bonus


def _retrieve_evidence_rows(state: dict, rejected_source_ids: set[str], top_k: int = 3) -> list[dict]:
    # docs/operation_dashboard.md의 STEP2 흐름처럼 chunk를 찾고 문서 원문과 다시 연결한다.
    ticket_id = _first(state["qa_ticket"])["ticket_id"]
    first_input = build_first_input_payload(ticket_id=ticket_id)
    knowledge_base = first_input["knowledge_base"]
    analysis = _first(state["ticket_analysis"])
    query_tokens = set(_tokenize(_build_query_text(state)))
    documents = {
        row["documents_id"]: row for row in knowledge_base.get("documents", []) if row.get("documents_id")
    }
    scored_rows: list[tuple[float, dict, dict]] = []
    for chunk in knowledge_base.get("documents_chunks", []):
        document = documents.get(chunk.get("document_id"))
        if not document:
            continue
        source_id = str(document.get("documents_id", ""))
        if rejected_source_ids and source_id in rejected_source_ids:
            continue
        score = _score_chunk(chunk, document, query_tokens, str(analysis.get("category", "")))
        if score <= 0:
            continue
        scored_rows.append((score, chunk, document))

    if not scored_rows and rejected_source_ids:
        # 모든 근거가 제외되면 한 번은 제한을 풀고 다시 검색한다.
        return _retrieve_evidence_rows(state, set(), top_k=top_k)

    scored_rows.sort(key=lambda item: item[0], reverse=True)
    draft_id = _first(state["answer_draft"])["draft_id"] + 1
    evidence_rows: list[dict] = []
    for rank, (score, _chunk, document) in enumerate(scored_rows[:top_k], start=1):
        evidence_rows.append(
            {
                "evidence_id": draft_id * 10 + rank,
                "draft_id": draft_id,
                "source_type": document["source_type"],
                "source_id": document["documents_id"],
                "evidence_text": document["raw_content"],
                "relevance_score": round(score, 3),
                "retrieval_rank": rank,
            }
        )
    return evidence_rows


def _compose_regenerated_draft(state: dict, evidence_rows: list[dict]) -> str:
    # 검색된 근거 범위 안에서만 답변을 다시 구성한다.
    deliveries = state["operation_logs"].get("item_delivery_logs", [])
    refunds = state["operation_logs"].get("refunds", [])
    payment_success = any(row.get("payment_status") == "success" for row in state["operation_logs"].get("payments", []))
    delivery_fail = any(row.get("delivery_status") == "fail" for row in deliveries)
    refund_pending = any(row.get("refund_status") == "pending" for row in refunds)
    evidence_map = {row["source_id"]: row["evidence_text"] for row in evidence_rows}

    sentences: list[str] = []
    if payment_success:
        sentences.append("결제 내역은 정상적으로 확인되었습니다.")
    if delivery_fail:
        sentences.append("다만 아이템 지급 로그가 실패 상태로 확인되어 운영 검토가 필요합니다.")
    if "FAQ-102" in evidence_map:
        sentences.append("우선 지급 로그와 수령 여부를 함께 확인해야 합니다.")
    if "POLICY-204" in evidence_map:
        sentences.append("지급 실패가 확인된 경우 운영팀이 수동 지급 또는 후속 조치를 검토합니다.")
    if "NOTICE-330" in evidence_map:
        sentences.append("동일한 지급 이슈가 반복되면 긴급 검토 대상으로 분류될 수 있습니다.")
    if refund_pending:
        sentences.append("현재 환불 요청이 접수된 상태라면 지급 검토와 함께 환불 진행 여부도 같이 확인됩니다.")
    if not sentences:
        sentences.append("확인 가능한 근거 문서를 기준으로 현재 문의 내용을 다시 검토 중입니다.")
    return " ".join(sentences)


def _regenerate_answer_draft(state: dict, rejected_source_ids: set[str]) -> dict:
    # reject 시 STEP2 성격의 검색과 초안 생성을 다시 수행한 뒤 approval 입력 형태로 복원한다.
    updated = clone_payload(state)
    draft = _first(updated["answer_draft"])
    evidence_rows = _retrieve_evidence_rows(updated, rejected_source_ids)
    draft_id = draft["draft_id"] + 1
    updated["answer_draft"] = [
        {
            "draft_id": draft_id,
            "ticket_id": draft["ticket_id"],
            "analysis_id": draft["analysis_id"],
            "draft_text": _compose_regenerated_draft(updated, evidence_rows),
            "prompt_version": f"{draft.get('prompt_version', 'v1')}_retry",
            "created_at": draft.get("created_at"),
        }
    ]
    updated["evidence_docs"] = evidence_rows
    updated.pop("evidence_alignment", None)
    updated.pop("safety_results", None)
    updated.pop("approval_decision", None)
    updated.pop("approval_result", None)
    updated.pop("human_review_request", None)
    updated.pop("final_outcome", None)
    return approval_core_chain.invoke(updated)


def _edit_answer_only(state: dict) -> dict:
    # 운영자가 초안을 직접 고치면 수정된 문장으로 다시 승인 점검을 수행한다.
    edited = input("수정할 답변을 입력하세요: ").strip()
    if not edited:
        print("빈 답변은 사용할 수 없습니다.")
        return state
    updated = clone_payload(state)
    draft = _first(updated["answer_draft"])
    draft["draft_text"] = edited
    return approval_core_chain.invoke(updated)


def _print_review_screen(state: dict) -> None:
    draft = _first(state["answer_draft"])
    print("\n[ANSWER_DRAFT]")
    print(draft["draft_text"])
    print("\n[EVIDENCE_DOCS]")
    print(json.dumps(state["evidence_docs"], ensure_ascii=False, indent=2))
    print("\n[APPROVAL_DECISION]")
    print(json.dumps(state["approval_decision"], ensure_ascii=False, indent=2))


def _review_answer_draft(state: dict, rejected_source_ids: set[str]) -> dict:
    # 사용자는 항상 answer_draft를 먼저 확인하고 approve/edit/reject 중 하나를 선택한다.
    while True:
        _print_review_screen(state)
        choice = input("decision [approved/edit/reject]: ").strip().lower()
        if choice == "approved":
            return mark_answer_draft_approved(state, operator_action="approve_final_answer", review_reason="운영자 최종 승인")
        if choice == "edit":
            edited_state = _edit_answer_only(state)
            return mark_answer_draft_approved(
                edited_state,
                operator_action="operator_edited_answer",
                review_reason="운영자가 답변 초안을 직접 수정 후 승인",
            )
        if choice == "reject":
            current_sources = {row["source_id"] for row in state.get("evidence_docs", []) if row.get("source_id")}
            rejected_source_ids.update(current_sources)
            print("\n초안을 반려했습니다. 근거 문서를 다시 검색하고 새 답변 초안을 생성합니다.")
            return _regenerate_answer_draft(state, rejected_source_ids)
        print("approved, edit, reject 중 하나를 입력하세요.")


def main() -> None:
    # docs 기준상 Approval Gate는 STEP2 산출물(answer_draft, evidence_docs)을 검토한 뒤 최종 승인으로 이어진다.
    state = approval_core_chain.invoke({})
    rejected_source_ids: set[str] = set()

    while True:
        reviewed_state = _review_answer_draft(state, rejected_source_ids)
        if reviewed_state.get("approval_result") == "approved":
            state = final_outcome_chain.invoke(reviewed_state)
            print("\n[FINAL_OUTCOME]")
            print(json.dumps(state["final_outcome"], ensure_ascii=False, indent=2))
            print("\n[FINAL_PAYLOAD]")
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return
        state = reviewed_state


if __name__ == "__main__":
    main()
