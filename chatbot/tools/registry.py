from __future__ import annotations

from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import (
    append_qa_ticket_message,
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    read_refunds,
    write_answer_draft,
    write_evidence_docs,
    write_failed_query,
    write_qa_ticket,
    write_safety_results,
    write_ticket_analysis,
    write_voc_feedback,
)
from chatbot.tools.vector_tools import embed_query, rerank_documents, search_documents


CHATBOT_TOOLS = [
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
    append_qa_ticket_message,
    write_failed_query,
    write_voc_feedback,
]

