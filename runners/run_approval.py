from __future__ import annotations
import json
from rootsetting import ensure_project_root_on_path
ensure_project_root_on_path()
from data.seed_payload import clone_payload
from operation.approvalagent.chain import approval_core_chain, approval_review_chain, final_outcome_chain

def _edit_answer_only(state: dict) -> dict:
    edited = input("edited answer text: ").strip()
    if not edited:
        print("빈 답변은 허용되지 않습니다.")
        return state
    updated = clone_payload(state)
    draft = updated["answer_draft"][0] if isinstance(updated["answer_draft"], list) else updated["answer_draft"]
    draft["draft_text"] = edited
    return approval_core_chain.invoke(updated)


def review(label: str, state: dict, value: dict) -> dict:
    print(f"\n[REVIEW] {label}")
    draft = state["answer_draft"][0] if isinstance(state["answer_draft"], list) else state["answer_draft"]
    print(f"\n[ANSWER_DRAFT]\n{draft['draft_text']}")
    print(f"\n[{label.upper()}]")
    print(json.dumps(value, ensure_ascii=False, indent=2))
    while True:
        choice = input("decision [approve/edit/reject]: ").strip().lower()
        if choice == "approve":
            return state
        if choice == "edit":
            return _edit_answer_only(state)
        if choice == "reject":
            raise RuntimeError(f"{label} rejected by operator")


def main() -> None:
    state = approval_core_chain.invoke({})
    if state["approval_result"] != "approved":
        state = approval_review_chain.invoke(state)
        state = review("human_review_request", state, state["human_review_request"])
        state = approval_review_chain.invoke(state)
    state = final_outcome_chain.invoke(state)
    state = review("final_outcome", state, state["final_outcome"])
    state = final_outcome_chain.invoke(state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
