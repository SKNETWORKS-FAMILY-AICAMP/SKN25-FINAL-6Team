"""Prompt builders for the operation workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .state import EvidenceDocument, OperationState, QueryRoute, RiskLevel, TargetRoute


class PromptModel(BaseModel):
    """Base prompt response model."""

    model_config = ConfigDict(extra="forbid")


class QueryRoutingResponse(PromptModel):
    """LLM output for query routing."""

    query_route: QueryRoute
    route_reason: str


class TicketAnalysisResponse(PromptModel):
    """LLM output for ticket analysis."""

    query_route: QueryRoute
    target_route: TargetRoute
    risk_level: RiskLevel
    risk_reason: str
    summary: str
    required_actions: list[str] = Field(default_factory=list)


class AnswerDraftResponse(PromptModel):
    """LLM output for a grounded customer answer draft."""

    answer_draft: str
    evidence_doc_ids: list[str] = Field(default_factory=list)


class UrgentDraftResponse(PromptModel):
    """LLM output for an urgent operator alert draft."""

    urgent_draft: str


class SafetyReviewResponse(PromptModel):
    """LLM output for approval gate safety review."""

    approved: bool
    evidence_matched: bool
    hallucination_detected: bool
    policy_violation_detected: bool
    unsafe_expression_detected: bool
    reasons: list[str] = Field(default_factory=list)


class HumanReviewResponse(PromptModel):
    """LLM output that prepares a review recommendation for operators."""

    decision: str
    reason: str
    edited_answer: str | None = None


SYSTEM_PROMPT = """You are an operation workflow assistant for a game customer-support system.
Use only the ticket, database context, and retrieved evidence provided in the prompt.
Return only JSON that matches the requested schema.
Do not invent user data, payment state, refund state, item delivery state, policy text, or incident status."""


QUERY_ROUTER_PROMPT = """Classify the ticket into one query route.

Allowed query_route values:
- payment: payment, purchase, transaction, billing, currency, product payment status
- refund: refund request, refund failure, refund policy application
- item_delivery: purchased or rewarded item delivery, missing item, delayed item
- gacha: gacha pull, banner, rarity, pity count, probability issue
- policy: game policy, notice, official guide, terms, normal help request
- abuse: abusive content, harassment, exploit, account abuse, policy-risk user behavior
- outage: service failure, incident, outage, access failure, widespread disruption

Ticket and context:
{state_json}"""


ANALYSIS_PROMPT = """Analyze the ticket using the selected route and database context.

Set target_route to urgent_alert only when the case needs immediate operator attention, such as critical risk, outage, abuse escalation, policy violation, payment/refund risk, or missing authoritative evidence for a high-impact decision.
Otherwise set target_route to rag_reply.

Ticket and context:
{state_json}"""


ANSWER_PROMPT = """Write a Korean customer-support answer draft grounded in retrieved evidence and database context.

Rules:
- Answer directly and politely.
- Use database context only when it belongs to this ticket/user/account.
- Cite evidence by returning evidence_doc_ids.
- If evidence is insufficient, say what should be checked by an operator.

Ticket, context, analysis, and evidence:
{state_json}"""


URGENT_PROMPT = """Write a concise Korean urgent alert draft for an operator.

Include ticket id, route, risk level, risk reason, relevant database context, and required actions.

Workflow state:
{state_json}"""


SAFETY_PROMPT = """Review the answer draft before final publication.

Check:
- Whether the draft is grounded in retrieved evidence and database context.
- Whether hallucination is present.
- Whether policy violation is present.
- Whether unsafe, defamatory, threatening, discriminatory, or overly definitive language is present.

Workflow state:
{state_json}"""


HUMAN_REVIEW_PROMPT = """Prepare an operator review recommendation for the answer draft.

decision must be one of approved, reject, edit.
Use edit when the answer can be fixed safely with a small correction.
Use reject when the workflow should reroute and regenerate.

Workflow state:
{state_json}"""


def render_state(state: OperationState) -> str:
    """Serialize workflow state for prompts."""

    return state.model_dump_json(exclude_none=True, ensure_ascii=False, indent=2)


def render_documents(documents: list[EvidenceDocument]) -> str:
    """Serialize retrieved documents for prompts."""

    return "\n".join(document.model_dump_json(exclude_none=True, ensure_ascii=False) for document in documents)
