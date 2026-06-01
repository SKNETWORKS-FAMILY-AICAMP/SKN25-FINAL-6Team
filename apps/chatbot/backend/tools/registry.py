from __future__ import annotations

from chatbot.tools.db_tools import (
    collect_user_payment_context,
    read_gacha_logs,
    read_item_delivery_logs,
)

PAYMENT_TOOLS = [
    collect_user_payment_context,
]

FAQ_TOOLS = [
]

BUG_TOOLS = [
    read_gacha_logs,
    read_item_delivery_logs,
]
