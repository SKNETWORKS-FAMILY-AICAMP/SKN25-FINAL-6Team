from typing import Any

from langchain.agents import create_agent

from config import settings
from operation.tools import (
    identify_account,
    load_input_payload,
    load_qa_ticket,
    lookup_operation_logs,
    retrieve_policy_evidence,
    run_approval_gate,
)


OPERATION_TOOLS = [
    load_input_payload,
    load_qa_ticket,
    identify_account,
    lookup_operation_logs,
    retrieve_policy_evidence,
    run_approval_gate,
]


def build_operation_agent() -> Any:
    return create_agent(
        model=settings.openai_model,
        tools=OPERATION_TOOLS,
        system_prompt=(
            "You are the operation batch agent. Execute STEP1 and STEP2 in one run. "
            "Use the first input payload as the only source of truth. Do not assume any DB access. "
            "STEP1: inspect the payload with tools, then create ticket_analysis yourself with category, "
            "risk_level, sentiment, routing_target, relevance_score, and summary. "
            "routing_target must be either rag_reply or urgent_alert. risk_level must be one of LOW, MEDIUM, HIGH. "
            "STEP2: build a retrieval query from the ticket and routing result, call retrieve_policy_evidence, "
            "then create answer_draft and evidence_docs yourself from the retrieved documents. "
            "After drafting, call run_approval_gate with the ticket_id, draft_text, risk_level, routing_target, "
            "and evidence_count. "
            "Return one compact JSON object with exactly these top-level keys: "
            "ticket_analysis, answer_draft, evidence_docs, safety_results, approval_result, final_outcome. "
            "ticket_analysis must include analysis_id, ticket_id, category, responder_type, risk_level, sentiment, "
            "relevance_score, routing_target, summary, analyzed_at. "
            "answer_draft must include draft_id, ticket_id, analysis_id, draft_text, prompt_version, created_at. "
            "Each evidence_docs item must include draft_id, source_type, source_id, title, chunk_id, evidence_text, "
            "relevance_score, retrieval_rank. "
            "Keep ids stable with analysis_id=5001 and draft_id=3001. Do not aggregate metrics or create dashboard insights."
        ),
    )


agent = build_operation_agent()
