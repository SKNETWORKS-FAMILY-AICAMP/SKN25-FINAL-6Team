from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

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
        ):
            account_service.login_with_credentials("USER1@game.com", "password", "KR")

        self.assertEqual(captured["email"], "USER1@game.com")


if __name__ == "__main__":
    unittest.main()
