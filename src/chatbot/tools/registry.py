from __future__ import annotations

from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    read_refunds,
)

PAYMENT_TOOLS = [
    read_payments,
    read_refunds,
    read_item_delivery_logs,
]

FAQ_TOOLS = [
]

BUG_TOOLS = [
    read_gacha_logs,
    read_item_delivery_logs,
]
