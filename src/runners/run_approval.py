from __future__ import annotations

import json

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from operation.approvalagent.chain import (
    approval_core_chain,
    apply_human_review_resolution,
    build_human_review_request,
    build_urgent_alert_payload,
    final_outcome_chain,
)


def _first(value: object) -> dict:
    return value[0] if isinstance(value, list) else value


def _print_state(state: dict) -> None:
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
    print("\n[FINAL_OUTCOME]")
    print(json.dumps(state["final_outcome"], ensure_ascii=False, indent=2))
    print("\n[FINAL_PAYLOAD]")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def _print_urgent_alert(state: dict) -> None:
    print("\n[URGENT_ALERT_PAYLOAD]")
    print(json.dumps(state["urgent_alert_payload"], ensure_ascii=False, indent=2))
    print("\n[FINAL_PAYLOAD]")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def _resolve_human_step(state: dict) -> dict:
    reviewed = build_human_review_request(state)
    print("\n[HUMAN_REVIEW_REQUEST]")
    print(json.dumps(reviewed["human_review_request"], ensure_ascii=False, indent=2))

    print("\noperator_action options: answer_edit, manual_payout, refund_process, urgent_response, approve_as_is")
    operator_action = input("operator_action: ").strip() or "approve_as_is"
    review_note = input("review_note: ").strip() or "operator reviewed the case"

    edited_draft_text: str | None = None
    if operator_action == "answer_edit":
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
    # README 상단 Mermaid flow:
    # DRAFT + EVIDENCE -> CHECK -> SAFETY -> RESULT
    # approved => FINAL
    # human_review => HUMAN -> FINAL
    # urgent_alert => EMAIL
    state = approval_core_chain.invoke({})
    _print_state(state)

    if state["approval_result"] == "approved":
        _print_final(final_outcome_chain.invoke(state))
        return

    if state["approval_result"] == "human_review":
        reviewed_state = _resolve_human_step(state)
        _print_final(final_outcome_chain.invoke(reviewed_state))
        return

    _print_urgent_alert(build_urgent_alert_payload(state))


if __name__ == "__main__":
    main()
