from __future__ import annotations

from unittest.mock import patch

from api.main import AdminLoginRequest, api_login_operator


def test_api_login_operator_trace_excludes_password() -> None:
    trace_calls: list[dict[str, object]] = []

    def capture_trace(*args, **kwargs):
        trace_calls.append(kwargs)

    with (
        patch("api.main.link_cs_auto_trace", capture_trace),
        patch("api.main.verify_admin_user_credentials", return_value={"authenticated": False, "reason": "invalid_credentials"}),
    ):
        result = api_login_operator(AdminLoginRequest(login_id="ops1", password="super-secret"))

    assert result["ok"] is False
    assert trace_calls
    assert trace_calls[0]["input_payload"] == {"login_id": "ops1"}
    assert "password" not in trace_calls[0]["input_payload"]
