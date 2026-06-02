"""
admin_users 테이블 조회에서 로그인 가능 여부 확인하는 코드.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from utils.passwords import verify_password


def verify_admin_login(login_id: str, password: str) -> dict[str, Any]:
    normalized_login_id = login_id.strip()

    try:
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        admin_id,
                        login_id,
                        password_hash,
                        display_name,
                        role,
                        status,
                        last_login_at,
                        password_updated_at,
                        created_at
                    FROM public.admin_users
                    WHERE login_id = %s
                    LIMIT 1
                    """,
                    (normalized_login_id,),
                )
                admin = cur.fetchone()

                if not admin or not verify_password(password, admin.get("password_hash")):
                    return {
                        "status": "ok",
                        "login_success": False,
                        "admin_id": None,
                        "login_id": normalized_login_id,
                        "display_name": None,
                        "role": None,
                        "message": "Login ID or password is invalid.",
                    }

                if admin.get("status") != "active":
                    return {
                        "status": "ok",
                        "login_success": False,
                        "admin_id": admin["admin_id"],
                        "login_id": admin["login_id"],
                        "display_name": admin.get("display_name"),
                        "role": admin.get("role"),
                        "message": "This admin account is inactive.",
                    }

                cur.execute(
                    """
                    UPDATE public.admin_users
                    SET last_login_at = CURRENT_TIMESTAMP
                    WHERE admin_id = %s
                    """,
                    (admin["admin_id"],),
                )
                conn.commit()

                return {
                    "status": "ok",
                    "login_success": True,
                    "admin_id": admin["admin_id"],
                    "login_id": admin["login_id"],
                    "display_name": admin.get("display_name") or admin["login_id"],
                    "role": admin.get("role"),
                    "message": "Login succeeded.",
                }
## 예외처리        
    except Exception as exc: 
        return {
            "status": "error",
            "error": str(exc),
            "login_success": False,
            "admin_id": None,
            "login_id": normalized_login_id,
            "display_name": None,
            "role": None,
            "message": "Failed to query admin account information.",
        }
