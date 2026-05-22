from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.common.db.connection import db_connection

from chatbot.repository.base import safe_read
from chatbot.utils.passwords import verify_password


def verify_user_login(email: str, password: str) -> dict[str, Any]:
    """Verify a user login with community_users.email and password_hash."""

    normalized_email = email.strip().lower()

    def _read() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
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
                        ga.account_status
                    FROM public.community_users cu
                    LEFT JOIN public.game_accounts ga
                        ON ga.user_id = cu.user_id
                    WHERE lower(cu.email) = %s
                    ORDER BY
                        CASE WHEN ga.account_status = 'active' THEN 0 ELSE 1 END,
                        ga.account_id
                    LIMIT 1
                    """,
                    (normalized_email,),
                )
                user = cur.fetchone()

        if not user or not verify_password(password, user.get("password_hash")):
            return {
                "status": "ok",
                "login_success": False,
                "user_id": None,
                "account_id": None,
                "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
            }

        if user.get("user_status") != "active":
            return {
                "status": "ok",
                "login_success": False,
                "user_id": user["user_id"],
                "account_id": None,
                "message": "사용할 수 없는 사용자 계정입니다.",
            }

        if user.get("account_id") is None or user.get("account_status") != "active":
            return {
                "status": "ok",
                "login_success": False,
                "user_id": user["user_id"],
                "account_id": user.get("account_id"),
                "message": "사용 가능한 게임 계정이 없습니다.",
            }

        return {
            "status": "ok",
            "login_success": True,
            "user_id": user["user_id"],
            "account_id": user["account_id"],
            "email": user["email"],
            "uid": user.get("uid"),
            "game_name": user.get("game_name"),
            "nickname": user.get("nickname"),
            "message": "로그인 성공",
        }

    return safe_read(operation="verify_user_login", reader=_read)

