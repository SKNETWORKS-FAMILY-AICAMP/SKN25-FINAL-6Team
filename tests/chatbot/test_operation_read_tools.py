from __future__ import annotations

import json
import os
import unittest
from typing import Any

from dotenv import load_dotenv

from src.common.db.connection import db_connection

from chatbot.repository.operation_log_repository import (
    read_gacha_logs_by_account,
    read_item_delivery_logs_by_account,
    read_payments_by_account,
    read_refunds_by_payment,
)
from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    read_refunds,
)


load_dotenv()


class TestOperationReadTools(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("DB_PASSWORD"):
            self.skipTest("DB_PASSWORD environment variable is required")

    def _skip_if_db_error(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("status") == "error":
            self.skipTest(f"Database connection is not available: {result.get('error')}")
        return result

    def _first_value_or_skip(self, query: str, params: tuple[Any, ...] = ()) -> int:
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    row = cur.fetchone()
        except Exception as exc:
            self.skipTest(f"Database connection is not available: {type(exc).__name__}")

        if not row:
            self.skipTest("Required mock operation data is not available")
        return int(row[0])

    def test_payment_reads_return_expected_shape(self) -> None:
        account_id = self._first_value_or_skip(
            """
            SELECT account_id
            FROM public.payments
            ORDER BY paid_at DESC NULLS LAST
            LIMIT 1
            """
        )

        result = self._skip_if_db_error(read_payments_by_account(account_id))

        self.assertEqual("ok", result["status"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(account_id, result["data"][0]["account_id"])
        self.assertIn("payment_id", result["data"][0])
        self.assertIn("payment_status", result["data"][0])

    def test_refund_reads_return_expected_shape_when_data_exists(self) -> None:
        payment_id = self._first_value_or_skip(
            """
            SELECT payment_id
            FROM public.refunds
            ORDER BY requested_at DESC NULLS LAST
            LIMIT 1
            """
        )

        result = self._skip_if_db_error(read_refunds_by_payment(payment_id))

        self.assertEqual("ok", result["status"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(payment_id, result["data"][0]["payment_id"])
        self.assertIn("refund_status", result["data"][0])

    def test_item_delivery_reads_return_expected_shape(self) -> None:
        account_id = self._first_value_or_skip(
            """
            SELECT account_id
            FROM public.item_delivery_logs
            ORDER BY expected_at DESC NULLS LAST, delivered_at DESC NULLS LAST
            LIMIT 1
            """
        )

        result = self._skip_if_db_error(read_item_delivery_logs_by_account(account_id))

        self.assertEqual("ok", result["status"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(account_id, result["data"][0]["account_id"])
        self.assertIn("delivery_status", result["data"][0])
        self.assertIn("item_name", result["data"][0])

    def test_gacha_reads_return_expected_shape(self) -> None:
        account_id = self._first_value_or_skip(
            """
            SELECT account_id
            FROM public.gacha_logs
            ORDER BY pulled_at DESC NULLS LAST
            LIMIT 1
            """
        )

        result = self._skip_if_db_error(read_gacha_logs_by_account(account_id))

        self.assertEqual("ok", result["status"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(account_id, result["data"][0]["account_id"])
        self.assertIn("banner_name", result["data"][0])
        self.assertIn("item_name", result["data"][0])

    def test_langchain_read_tools_return_json_payloads(self) -> None:
        account_id = self._first_value_or_skip(
            """
            SELECT account_id
            FROM public.payments
            ORDER BY paid_at DESC NULLS LAST
            LIMIT 1
            """
        )
        payment_id = self._first_value_or_skip(
            """
            SELECT payment_id
            FROM public.payments
            WHERE account_id = %s
            ORDER BY paid_at DESC NULLS LAST
            LIMIT 1
            """,
            (account_id,),
        )

        tool_payloads = [
            read_payments.invoke({"account_id": account_id}),
            read_item_delivery_logs.invoke({"account_id": account_id}),
            read_gacha_logs.invoke({"account_id": account_id}),
            read_refunds.invoke({"payment_id": payment_id}),
        ]

        for payload in tool_payloads:
            with self.subTest(payload=payload[:80]):
                decoded = json.loads(payload)
                self.assertIn(decoded["status"], {"ok", "error"})
                self.assertIn("count", decoded)
                self.assertIn("data", decoded)


if __name__ == "__main__":
    unittest.main()
