from __future__ import annotations

import json
from datetime import datetime, timezone

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from config import PAYLOAD_MARKER
from data.seed_payload import FIRST_INPUT_PAYLOAD
from operation.agent import agent as step12_agent
from operation.approvalagent.chain import approval_chain
from operation.step12agent.prompts import RUN_INSTRUCTION


def _now_iso() -> str:
    # UTC 기준 ISO 8601 형식; DB의 checked_at, created_at 컬럼 타입에 맞춘다
    return datetime.now(timezone.utc).isoformat()


def _adapt(step12_result: dict, source_payload: dict) -> dict:
    """step12agent 출력을 approvalagent ApprovalPayload 형태로 변환한다.

    두 에이전트의 포맷 차이:
    - ticket_analysis : step12 dict  → approval list[dict] (analysis_id, ticket_id 보강)
    - answer_draft    : step12 str   → approval list[dict] (draft_id, draft_text 래핑)
    - evidence_docs   : step12 list  → approval list (evidence_id, draft_id 보강)

    DB 연동 전이므로 analysis_id, draft_id, evidence_id는 임시값 0을 사용한다.
    DB INSERT 완료 후에는 반환된 실제 PK 값으로 교체해야 한다.
    """
    # source_payload에서 ticket_id를 추출해 ticket_analysis, answer_draft 두 곳에 주입한다
    ticket_id: int = source_payload["qa_ticket"]["ticket_id"]

    # step12agent가 도구를 호출하지 않은 경우 None이 될 수 있으므로 방어적 폴백을 적용한다
    ticket_analysis = step12_result.get("ticket_analysis") or {}
    answer_draft_text: str = step12_result.get("answer_draft") or ""
    evidence_docs: list = step12_result.get("evidence_docs") or []

    # approvalagent의 _first()가 list[0]을 꺼내므로 반드시 list로 래핑해야 한다
    adapted_ticket_analysis = [{"analysis_id": 0, "ticket_id": ticket_id, **ticket_analysis}]

    # answer_draft는 step12agent에서 문자열로 반환되므로 DDL 구조(dict)로 감싼다
    # prompt_version은 별도 상수가 없어 "v1" 리터럴을 사용한다
    adapted_answer_draft = [
        {
            "draft_id": 0,
            "ticket_id": ticket_id,
            "analysis_id": 0,
            "draft_text": answer_draft_text,
            "prompt_version": "v1",
            "created_at": _now_iso(),
        }
    ]

    # approvalagent가 evidence_id로 근거를 식별하므로 중복 없이 1-indexed 순번을 부여한다
    adapted_evidence_docs = [
        {"evidence_id": i + 1, "draft_id": 0, **doc}
        for i, doc in enumerate(evidence_docs)
    ]

    return {
        # qa_ticket, account_context, operation_logs는 원본 payload를 그대로 전달한다
        "qa_ticket": source_payload["qa_ticket"],
        "account_context": source_payload["account_context"],
        "operation_logs": source_payload["operation_logs"],
        "ticket_analysis": adapted_ticket_analysis,
        "answer_draft": adapted_answer_draft,
        "evidence_docs": adapted_evidence_docs,
    }


def main() -> None:
    """step12agent(STEP1+STEP2) → approvalagent 전체 파이프라인을 1회 실행한다.

    실 DB 연동 전 임시 방식; 연동 후에는 DB에서 QA_ticket을 읽는 방식으로 교체 예정.
    """
    # run_operation.py와 동일한 메시지 조립 방식으로 step12agent를 호출한다
    step12_result = step12_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{RUN_INSTRUCTION}"
                        f"{PAYLOAD_MARKER}{json.dumps(FIRST_INPUT_PAYLOAD, ensure_ascii=True, indent=2)}"
                    ),
                }
            ]
        }
    )

    print("[STEP1+STEP2 완료]")
    print(f"ticket_analysis : {json.dumps(step12_result.get('ticket_analysis'), ensure_ascii=False)}")
    # 긴 초안은 앞 80자만 표시해 터미널 출력을 간결하게 유지한다
    print(f"answer_draft    : {(step12_result.get('answer_draft') or '')[:80]}...")

    # step12agent 출력 포맷을 approvalagent 입력 포맷으로 변환한다
    approval_input = _adapt(step12_result, FIRST_INPUT_PAYLOAD)

    # approval_chain: load → alignment_check → safety_score → decision (approvalagent/chain.py 참조)
    approval_result = approval_chain.invoke(approval_input)

    print("\n[APPROVAL_RESULT]")
    print(approval_result.get("approval_result"))

    # approval_result 값에 따라 최종 결과 키가 달라지므로 우선순위 순으로 꺼낸다
    # approved → final_outcome / human_review → human_review_request / urgent_alert → urgent_alert_payload
    final = (
        approval_result.get("final_outcome")
        or approval_result.get("human_review_request")
        or approval_result.get("urgent_alert_payload")
    )
    print("\n[FINAL]")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
