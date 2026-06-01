from __future__ import annotations

from typing import Any

from repository.account_repository import verify_user_login


def login_with_credentials(email: str, password: str, server_region: str) -> dict[str, Any]:
    normalized_email = email.strip()
    normalized_region = server_region.strip()
    if not normalized_email or not password or not normalized_region:
        return {
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "game_id": "",
            "email": normalized_email,
            "server_region": normalized_region,
            "nickname": None,
            "message": "Email, password, and server region are required.",
        }

    result = verify_user_login(normalized_email, password, normalized_region)
    if result.get("status") != "ok":
        return {
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "game_id": "",
            "email": normalized_email,
            "server_region": normalized_region,
            "nickname": None,
            "message": "Account lookup failed.",
        }

    return {
        "login_success": bool(result.get("login_success")),
        "user_id": result.get("user_id"),
        "account_id": result.get("account_id"),
        "game_id": result.get("game_id") or result.get("uid") or "",
        "email": result.get("email") or normalized_email,
        "server_region": result.get("server_region") or normalized_region,
        "nickname": result.get("nickname"),
        "message": result.get("message") or "Login succeeded.",
    }
