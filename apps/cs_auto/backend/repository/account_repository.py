from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection

from utils.passwords import verify_password


def verify_user_login(
    email: str,
    password: str,
    server_region: str | None = None,
) -> dict[str, Any]:
    """Verify a user login with community_users.email/password_hash and an optional server."""
    normalized_email = email.strip()
    normalized_region = server_region.strip() if server_region else None

    try:
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if normalized_region:
                    cur.execute(
                        """
                        SELECT
                            cu.user_id,
                            cu.email,
                            cu.nickname,
                            cu.user_status,
                            cu.password_hash,
                            ga.account_id,
                            ga.uid,
                            ga.game_name,
                            ga.server_region,
                            ga.account_status
                        FROM public.community_users cu
                        LEFT JOIN public.game_accounts ga
                            ON ga.user_id = cu.user_id
                        WHERE cu.email = %s
                          AND ga.server_region = %s
                        ORDER BY
                            CASE WHEN ga.account_status = 'active' THEN 0 ELSE 1 END,
                            ga.account_id
                        LIMIT 1
                        """,
                        (normalized_email, normalized_region),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            cu.user_id,
                            cu.email,
                            cu.nickname,
                            cu.user_status,
                            cu.password_hash,
                            ga.account_id,
                            ga.uid,
                            ga.game_name,
                            ga.server_region,
                            ga.account_status
                        FROM public.community_users cu
                        LEFT JOIN public.game_accounts ga
                            ON ga.user_id = cu.user_id
                        WHERE cu.email = %s
                        ORDER BY
                            CASE WHEN ga.account_status = 'active' THEN 0 ELSE 1 END,
                            ga.account_id
                        LIMIT 1
                        """,
                        (normalized_email,),
                    )
                user = cur.fetchone()
    except Exception as exc:  # pragma: no cover - thin DB wrapper
        return {
            "status": "error",
            "error": str(exc),
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "message": "Failed to query account information.",
        }

    if not user or not verify_password(password, user.get("password_hash")):
        return {
            "status": "ok",
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "message": "Email or password is invalid.",
        }

    if user.get("user_status") != "active":
        return {
            "status": "ok",
            "login_success": False,
            "user_id": user["user_id"],
            "account_id": None,
            "message": "This community account is inactive.",
        }

    if user.get("account_id") is None or user.get("account_status") != "active":
        return {
            "status": "ok",
            "login_success": False,
            "user_id": user["user_id"],
            "account_id": user.get("account_id"),
            "message": "No active game account is available for this server.",
        }

    return {
        "status": "ok",
        "login_success": True,
        "user_id": user["user_id"],
        "account_id": user["account_id"],
        "email": user["email"],
        "uid": user.get("uid"),
        "game_id": user.get("uid"),
        "game_name": user.get("game_name"),
        "nickname": user.get("nickname"),
        "server_region": user.get("server_region"),
        "message": "Login succeeded.",
    }
