from __future__ import annotations

import json

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from operation.approvalagent.chain import (
    approval_core_chain,
    apply_human_review_resolution,
    build_human_review_request,
    final_outcome_chain,
)


def _first(value: object) -> dict:
    return value[0] if isinstance(value, list) else value


def _print_state(state: dict) -> None:
    # DRAFT / EVIDENCE / SAFETY / RESULT 노드의 현재 상태를 화면에 출력한다.
    draft = _first(state["answer_draft"])
    print("\n[ANSWER_DRAFT]")
    print(draft["draft_text"])
    print("\n[EVIDENCE_DOCS]")
    print(json.dumps(state["evidence_docs"], ensure_ascii=False, indent=2))
    print("\n[SAFETY_RESULTS]")
    print(json.dumps(state["safety_results"], ensure_ascii=False, indent=2))
    print("\n[APPROVAL_DECISION]")
    print(json.dumps(state["approval_decision"], ensure_ascii=False, indent=2))


def _print_final(state: dict) -> None:
    # FINAL 노드 결과와 종료 시점 payload를 출력한다.
    print("\n[FINAL_OUTCOME]")
    print(json.dumps(state["final_outcome"], ensure_ascii=False, indent=2))
    print("\n[FINAL_PAYLOAD]")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def _resolve_human_step(state: dict) -> dict:
    # RESULT가 human_review 또는 urgent_alert일 때 HUMAN 노드의 수동 처리 내용을 받는다.
    reviewed = build_human_review_request(state)
    print("\n[HUMAN_REVIEW_REQUEST]")
    print(json.dumps(reviewed["human_review_request"], ensure_ascii=False, indent=2))

    # 운영자는 HUMAN 단계에서 답변 수정, 수동 지급, 환불 처리, 긴급 대응 중 하나를 수행한다.
    print("\noperator_action options: answer_edit, manual_payout, refund_process, urgent_response, approve_as_is")
    operator_action = input("operator_action: ").strip() or "approve_as_is"
    review_note = input("review_note: ").strip() or "operator reviewed the case"

    edited_draft_text: str | None = None
    if operator_action == "answer_edit":
        # HUMAN 단계에서 답변 수정이 필요한 경우 수정된 answer_draft를 직접 입력받는다.
        edited = input("edited_answer_draft: ").strip()
        if edited:
            edited_draft_text = edited

    return apply_human_review_resolution(
        reviewed,
        operator_action=operator_action,
        review_note=review_note,
        edited_draft_text=edited_draft_text,
    )


def main() -> None:
    # Mermaid flow 고정:
    # DRAFT + EVIDENCE -> CHECK -> SAFETY -> RESULT -> (approved => FINAL, else HUMAN -> FINAL)
    # approval_core_chain은 CHECK, SAFETY, RESULT까지를 순서대로 수행한다.
    state = approval_core_chain.invoke({})
    _print_state(state)

    if state["approval_result"] == "approved":
        # RESULT = approved 이면 HUMAN을 거치지 않고 바로 FINAL로 닫는다.
        final_state = final_outcome_chain.invoke(state)
        _print_final(final_state)
        return

    # RESULT = human_review 또는 urgent_alert 이면 반드시 HUMAN을 거친 뒤 FINAL로 간다.
    final_state = final_outcome_chain.invoke(_resolve_human_step(state))
    _print_final(final_state)


if __name__ == "__main__":
    main()
