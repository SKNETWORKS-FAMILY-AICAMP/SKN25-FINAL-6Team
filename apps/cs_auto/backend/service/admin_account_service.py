from __future__ import annotations

from typing import Any
# DB 조회 함수 불러와서 사용하기.
from repository.admin_account_repository import verify_admin_login


# login_admin_with_credentials ?? ??
def login_admin_with_credentials(login_id: str, password: str) -> dict[str, Any]:
    normalized_login_id = login_id.strip()
    if not normalized_login_id or not password:
        return {
            "login_success": False,
            "admin_id": None,
            "login_id": normalized_login_id,
            "display_name": None,
            "role": None,
            "message": "Login ID and password are required.",
        }

    result = verify_admin_login(normalized_login_id, password)
    if result.get("status") != "ok":
        return {
            "login_success": False,
            "admin_id": None,
            "login_id": normalized_login_id,
            "display_name": None,
            "role": None,
            "message": "Admin account lookup failed.",
        }

    return {
        "login_success": bool(result.get("login_success")),
        "admin_id": result.get("admin_id"),
        "login_id": result.get("login_id") or normalized_login_id,
        "display_name": result.get("display_name"),
        "role": result.get("role"),
        "message": result.get("message") or "Login succeeded.",
    }
