"""
프론트엔드에서 로그인하는 운영자가 실제로 운영자가 맞는지 admin_users 테이블 기준으로 확인하는 함수. 
이 함수에서 api 포인트를 만들어내서 프론트에 전달한다.
"""

from __future__ import annotations

import uuid

import bcrypt
from psycopg.rows import dict_row

from common.db.connection import db_connection


def verify_admin_user_credentials(login_id: str, password: str) -> dict[str, object]:
    """
    api.main.authenticate_operator가 호출할 운영자 인증 함수.

    예상 내용:
    - admin_users.login_id로 운영자 계정을 조회한다.
    - admin_users.status가 active인지 확인한다.
    - 입력받은 password를 password_hash와 비교한다.
    - 성공 시 admin_id, login_id, display_name, role을 반환한다.
    - 실패 시 비밀번호 원문이나 password_hash가 응답과 로그에 남지 않게 처리한다.
    """

    normalized_login_id = login_id.strip()
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT admin_id, login_id, password_hash, display_name, role, status
                FROM admin_users
                WHERE login_id = %s
                """,
                (normalized_login_id,),
            )
            admin_user = cur.fetchone()
            if admin_user is None:
                return {"authenticated": False, "reason": "invalid_credentials"}

            if admin_user["status"] != "active":
                return {"authenticated": False, "reason": "inactive_operator"}

            password_hash = str(admin_user["password_hash"])
            if not password_hash.startswith(("$2a$", "$2b$", "$2y$")) or len(password_hash) != 60:
                return {"authenticated": False, "reason": "invalid_credentials"}

            password_matches = bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
            if not password_matches:
                return {"authenticated": False, "reason": "invalid_credentials"}

            cur.execute(
                """
                UPDATE admin_users
                SET last_login_at = CURRENT_TIMESTAMP
                WHERE admin_id = %s
                """,
                (admin_user["admin_id"],),
            )
            # admin_event_logs 테이블 사용 중단으로 로그인 이벤트 적재는 비활성화한다.
            # cur.execute(
            #     """
            #     INSERT INTO admin_event_logs (
            #         node_name,
            #         event_type,
            #         status,
            #         metadata,
            #         actor_admin_id
            #     )
            #     VALUES (%s, %s, %s, %s, %s)
            #     """,
            #     (
            #         "cs_auto_auth",
            #         "login",
            #         "success",
            #         Json({"login_id": admin_user["login_id"], "role": admin_user["role"]}),
            #         admin_user["admin_id"],
            #     ),
            # )

    return {
        "authenticated": True,
        "admin_id": admin_user["admin_id"],
        "login_id": admin_user["login_id"],
        "display_name": admin_user["display_name"],
        "role": admin_user["role"],
        "status": admin_user["status"],
    }


def create_admin_session(admin_user: dict[str, object]) -> dict[str, object]:
    """
    로그인 성공 후 프론트엔드가 사용할 운영자 세션 정보를 만든다.

    예상 내용:
    - admin_id와 role을 기준으로 API 접근 범위를 정한다.
    - 세션 토큰 또는 쿠키 기반 인증 정보를 발급한다.
    - last_login_at 갱신에 필요한 값을 준비한다.
    """

    session_id = uuid.uuid4().hex
    return {
        "session_id": session_id,
        "admin_id": admin_user["admin_id"],
        "login_id": admin_user["login_id"],
        "display_name": admin_user["display_name"],
        "role": admin_user["role"],
    }


def revoke_admin_session(session_id: str | None, admin_id: int | None = None) -> dict[str, object]:
    """
    로그아웃 요청 시 운영자 세션을 무효화한다.

    예상 내용:
    - api.main.api_logout_operator에서 호출한다.
    - 세션 저장소나 토큰 블랙리스트 정책에 따라 현재 로그인 상태를 종료한다.
    - 로그아웃 처리 결과를 반환한다.
    """

    if admin_id is not None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                # admin_event_logs 테이블 사용 중단으로 로그아웃 이벤트 적재는 비활성화한다.
                # cur.execute(
                #     """
                #     INSERT INTO admin_event_logs (
                #         node_name,
                #         event_type,
                #         status,
                #         metadata,
                #         actor_admin_id
                #     )
                #     VALUES (%s, %s, %s, %s, %s)
                #     """,
                #     (
                #         "cs_auto_auth",
                #         "logout",
                #         "success",
                #         Json({"session_id": session_id}),
                #         admin_id,
                #     ),
                # )
                pass

    return {"revoked": True, "session_id": session_id, "admin_id": admin_id}
