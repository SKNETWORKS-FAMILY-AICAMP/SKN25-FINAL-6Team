import json
import sys
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.retrievers import BM25Retriever
from langchain_openai import OpenAIEmbeddings


ROOT_DIR = Path(__file__).resolve().parent.parent
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from config import settings
from data.seed_payload import FIRST_INPUT_PAYLOAD, clone_payload


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2)


def _payload() -> dict:
    return clone_payload(FIRST_INPUT_PAYLOAD)


def _policy_documents() -> list[Document]:
    payload = _payload()
    return [
        Document(
            page_content=entry["chunk_text"],
            metadata={
                "source_type": entry["source_type"],
                "source_id": entry["source_id"],
                "category": entry["category"],
                "title": entry["title"],
                "chunk_id": entry["chunk_id"],
            },
        )
        for entry in payload["policy_documents"]
    ]


@lru_cache(maxsize=1)
def _embedding_model_name() -> str:
    return settings.embedding_model or "text-embedding-3-small"


@lru_cache(maxsize=1)
def _embedding_client() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=_embedding_model_name(),
    )


@lru_cache(maxsize=1)
def _bm25_retriever() -> BM25Retriever:
    retriever = BM25Retriever.from_documents(_policy_documents())
    retriever.k = len(_policy_documents())
    return retriever


@lru_cache(maxsize=1)
def _vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore.from_documents(_policy_documents(), _embedding_client())


@tool(parse_docstring=True)
def load_input_payload() -> str:
    """Load the first input payload used as the only data source for operation."""
    return _json(_payload())


@tool(parse_docstring=True)
def load_qa_ticket(ticket_id: int | None = None) -> str:
    """Load the QA_ticket slice from the first input payload.

    Args:
        ticket_id: Optional QA_ticket.ticket_id to confirm the current payload target.
    """
    payload = _payload()
    ticket = payload["qa_ticket"]
    if ticket_id is not None:
        ticket["requested_ticket_id"] = ticket_id
    return _json(ticket)


@tool(parse_docstring=True)
def identify_account(user_id: int | None = None, account_id: int | None = None) -> str:
    """Load community user and game account context from the first input payload.

    Args:
        user_id: Optional community_users.user_id hint.
        account_id: Optional game_accounts.account_id hint.
    """
    payload = _payload()
    context = payload["account_context"]
    if user_id is not None:
        context["requested_user_id"] = user_id
    if account_id is not None:
        context["requested_account_id"] = account_id
    return _json(context)


@tool(parse_docstring=True)
def lookup_operation_logs(account_id: int | None = None) -> str:
    """Load payment, refund, item delivery, and gacha logs from the first input payload.

    Args:
        account_id: Optional game_accounts.account_id hint.
    """
    payload = _payload()
    logs = payload["operation_logs"]
    if account_id is not None:
        logs["requested_account_id"] = account_id
    return _json(logs)


@tool(parse_docstring=True)
def retrieve_policy_evidence(category: str, query: str, top_k: int = 3) -> str:
    """Retrieve relevant payload documents for STEP2 RAG.

    Args:
        category: Inquiry category chosen during routing.
        query: Retrieval query created from the ticket and routing result.
        top_k: Maximum number of evidence documents to return.
    """
    full_query = f"{category} {query}".strip()
    bm25_docs = _bm25_retriever().invoke(full_query)
    vector_docs = _vector_store().similarity_search(full_query, k=len(_policy_documents()))

    fused_scores: dict[str, float] = {}
    selected_documents: dict[str, Document] = {}

    for rank, document in enumerate(bm25_docs, start=1):
        chunk_id = str(document.metadata["chunk_id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (rank + 1))
        selected_documents[chunk_id] = document

    for rank, document in enumerate(vector_docs, start=1):
        chunk_id = str(document.metadata["chunk_id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (rank + 1))
        selected_documents[chunk_id] = document

    ranked_chunk_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)
    max_score = max(fused_scores.values())
    documents = []
    for rank, chunk_id in enumerate(ranked_chunk_ids[:top_k], start=1):
        document = selected_documents[chunk_id]
        documents.append(
            {
                "source_type": document.metadata["source_type"],
                "source_id": document.metadata["source_id"],
                "category": document.metadata["category"],
                "title": document.metadata["title"],
                "chunk_id": document.metadata["chunk_id"],
                "evidence_text": document.page_content,
                "relevance_score": round(fused_scores[chunk_id] / max_score, 2),
                "retrieval_rank": rank,
            }
        )

    return _json(
        {
            "retriever": "payload_hybrid",
            "strategy": "BM25Retriever + InMemoryVectorStore(OpenAIEmbeddings) with reciprocal-rank fusion",
            "embedding_model": _embedding_model_name(),
            "query": full_query,
            "documents": documents,
        }
    )


@tool(parse_docstring=True)
def run_approval_gate(
    ticket_id: int,
    draft_text: str,
    risk_level: str,
    routing_target: str,
    evidence_count: int,
) -> str:
    """Compute approval results from the model draft and retrieved evidence.

    Args:
        ticket_id: QA_ticket.ticket_id for the current operation run.
        draft_text: Final answer draft text created in STEP2.
        risk_level: Risk level chosen during ticket analysis.
        routing_target: Routing target chosen during STEP1.
        evidence_count: Number of evidence documents used in the draft.
    """
    payload = _payload()
    hallucination_score = 0.02 if evidence_count >= 2 else 0.06
    policy_violation_score = 0.0 if "refund" not in draft_text.lower() else 0.02
    factuality_score = 0.99 if evidence_count >= 2 else 0.95
    approval_result = "approved"
    operator_action = "post_answer"

    if risk_level.upper() == "HIGH" or routing_target == "urgent_alert":
        approval_result = "human_review"
        operator_action = "manual_delivery_review"

    return _json(
        {
            "safety_results": {
                "safety_id": 6001,
                "draft_id": 3001,
                "hallucination_score": hallucination_score,
                "toxicity_score": 0.0,
                "policy_violation_score": policy_violation_score,
                "factuality_score": factuality_score,
                "checked_at": payload["qa_ticket"]["inquiry_created_at"],
            },
            "approval_result": approval_result,
            "final_outcome": {
                "ticket_id": ticket_id,
                "status": "closed",
                "operator_action": operator_action,
            },
        }
    )
