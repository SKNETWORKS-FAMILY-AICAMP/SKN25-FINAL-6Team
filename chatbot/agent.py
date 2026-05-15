from __future__ import annotations

from langchain.agents import create_agent

from chatbot.schemas import ChatbotState
from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    read_refunds,
    write_answer_draft,
    write_evidence_docs,
    write_qa_ticket,
    write_safety_results,
    write_ticket_analysis,
)
from chatbot.tools.vector_tools import embed_query, rerank_documents, search_documents
from config import settings


CHATBOT_SYSTEM_PROMPT = """You are a game customer support chatbot agent.

Handle one customer ticket at a time. Use tools to read account/payment/game logs,
search FAQ or policy documents, and persist ticket processing outputs.

Required flow:
1. Identify the inquiry category: payment, in-game bug, FAQ, or VOC.
2. Persist the ticket if needed with write_qa_ticket.
3. Persist classification and routing details with write_ticket_analysis.
4. Use the relevant read/search tools before answering.
5. Persist the answer with write_answer_draft.
6. Persist evidence with write_evidence_docs when the answer used logs or documents.
7. Persist safety evaluation fields with write_safety_results when available.

For payment disputes or complicated bugs, make the answer conservative and mention
that an operator may review the ticket. For simple FAQ or low-risk inquiries, provide
a concise direct answer.
"""


agent = create_agent(
    model=settings.openai_model,
    tools=[
        read_payments,
        read_refunds,
        read_item_delivery_logs,
        read_gacha_logs,
        embed_query,
        search_documents,
        rerank_documents,
        get_cache,
        set_cache,
        write_qa_ticket,
        write_ticket_analysis,
        write_answer_draft,
        write_evidence_docs,
        write_safety_results,
    ],
    system_prompt=CHATBOT_SYSTEM_PROMPT,
    state_schema=ChatbotState,
)
