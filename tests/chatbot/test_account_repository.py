from __future__ import annotations

import os
import unittest

from dotenv import load_dotenv
from psycopg import Error as PsycopgError

from src.common.db.connection import db_connection

from chatbot.repository.account_repository import read_server_regions, verify_user_login


load_dotenv()


class TestAccountRepository(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("DB_PASSWORD"):
            self.skipTest("DB_PASSWORD environment variable is required")

    def _login_or_skip(
        self,
        *,
        email: str,
        password: str,
        server_region: str | None = None,
    ) -> dict:
        result = verify_user_login(email=email, password=password, server_region=server_region)
        if result.get("status") == "error":
            self.skipTest(f"Database connection is not available: {result.get('error')}")
        return result

    def test_read_server_regions_returns_available_regions(self) -> None:
        result = read_server_regions()
        if result.get("status") == "error":
            self.skipTest(f"Database connection is not available: {result.get('error')}")

        regions = {row["server_region"] for row in result.get("data", [])}
        self.assertTrue(regions)

    def test_active_user_can_login_with_email_password_and_region(self) -> None:
        result = self._login_or_skip(
            email="user1@game.com",
            password="test1",
            server_region="KR",
        )

        self.assertTrue(result["login_success"])
        self.assertEqual(1, result["user_id"])
        self.assertIsNotNone(result["account_id"])
        self.assertEqual("KR", result["server_region"])
        self.assertNotIn("password", result)
        self.assertNotIn("password_hash", result)

    def test_wrong_password_fails_login(self) -> None:
        result = self._login_or_skip(
            email="user1@game.com",
            password="wrong-password",
            server_region="KR",
        )

        self.assertFalse(result["login_success"])
        self.assertIsNone(result["account_id"])

    def test_unknown_email_fails_login(self) -> None:
        result = self._login_or_skip(
            email="missing-user@example.com",
            password="test1",
            server_region="KR",
        )

        self.assertFalse(result["login_success"])
        self.assertIsNone(result["user_id"])
        self.assertIsNone(result["account_id"])

    def test_suspended_user_fails_login(self) -> None:
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT cu.user_id, cu.email, ga.server_region
                        FROM public.community_users cu
                        JOIN public.game_accounts ga
                          ON ga.user_id = cu.user_id
                        WHERE cu.user_status <> 'active'
                          AND cu.password_hash IS NOT NULL
                          AND ga.server_region IS NOT NULL
                        ORDER BY cu.user_id
                        LIMIT 1
                        """
                    )
                    user = cur.fetchone()
        except PsycopgError as exc:
            self.skipTest(f"Database connection is not available: {type(exc).__name__}")

        if not user:
            self.skipTest("No suspended mock user with a linked game account is available")

        user_id, email, server_region = user
        result = self._login_or_skip(
            email=email,
            password=f"test{user_id}",
            server_region=server_region,
        )

        self.assertFalse(result["login_success"])
        self.assertEqual(user_id, result["user_id"])
        self.assertIsNone(result["account_id"])


if __name__ == "__main__":
    unittest.main()
