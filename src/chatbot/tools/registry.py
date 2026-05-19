from __future__ import annotations

from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    read_refunds,
    write_failed_query,
)
from chatbot.tools.vector_tools import embed_query, rerank_documents, search_documents

PAYMENT_TOOLS = [
    read_payments,
    read_refunds,
    read_item_delivery_logs,
]

FAQ_TOOLS = [
    embed_query,
    search_documents,
    rerank_documents,
    get_cache,
    set_cache,
    write_failed_query,
]

BUG_TOOLS = [
    read_gacha_logs,
    read_item_delivery_logs,
]
