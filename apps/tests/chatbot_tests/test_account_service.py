from __future__ import annotations

import unittest
from unittest.mock import patch

from chatbot.service import account_service


class TestAccountService(unittest.TestCase):
    def test_login_preserves_email_case_for_verification(self) -> None:
        captured: dict[str, str] = {}

        def fake_verify_user_login(email: str, password: str, server_region: str):
            captured["email"] = email
            return {
                "status": "ok",
                "login_success": False,
                "user_id": None,
                "account_id": None,
                "message": "invalid credentials",
            }

        with (
            patch.object(account_service, "verify_user_login", fake_verify_user_login),
            patch.object(account_service, "_log_login_result", lambda *args, **kwargs: None),
            patch.object(account_service, "link_current_trace", lambda *args, **kwargs: None),
        ):
            account_service.login_with_credentials("USER1@game.com", "password", "KR")

        self.assertEqual(captured["email"], "USER1@game.com")

    def test_login_trace_excludes_password_and_links_result_metadata(self) -> None:
        trace_calls: list[dict[str, object]] = []

        def fake_verify_user_login(email: str, password: str, server_region: str):
            self.assertEqual(password, "super-secret")
            return {
                "status": "ok",
                "login_success": True,
                "user_id": 7,
                "account_id": 101,
                "game_id": "g-1",
                "email": email,
                "server_region": server_region,
                "message": "ok",
            }

        def capture_trace(**kwargs):
            trace_calls.append(kwargs)

        with (
            patch.object(account_service, "verify_user_login", fake_verify_user_login),
            patch.object(account_service, "_log_login_result", lambda *args, **kwargs: None),
            patch.object(account_service, "link_current_trace", capture_trace),
        ):
            result = account_service.login_with_credentials("USER1@game.com", "super-secret", "KR")

        self.assertTrue(result["login_success"])
        self.assertEqual(len(trace_calls), 2)

        input_call = trace_calls[0]
        output_call = trace_calls[1]

        self.assertEqual(input_call["input_payload"], {"email": "USER1@game.com", "server_region": "KR"})
        self.assertNotIn("password", input_call["input_payload"])
        self.assertEqual(input_call["metadata"]["email"], "USER1@game.com")
        self.assertEqual(input_call["metadata"]["server_region"], "KR")

        self.assertEqual(output_call["user_id"], 7)
        self.assertEqual(output_call["output_payload"]["login_success"], True)
        self.assertEqual(output_call["output_payload"]["account_id"], 101)
        self.assertEqual(output_call["metadata"]["login_success"], True)
        self.assertEqual(output_call["metadata"]["game_id"], "g-1")
        self.assertEqual(output_call["metadata"]["db_status"], "ok")


if __name__ == "__main__":
    unittest.main()
