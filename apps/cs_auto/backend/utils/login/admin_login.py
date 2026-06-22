from __future__ import annotations

import uuid

import bcrypt
from psycopg.rows import dict_row

from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_cs_auto_trace


@observe_if_enabled(name="cs_auto_verify_admin_user_credentials", as_type="tool", tags=["cs-auto", "auth"])
def verify_admin_user_credentials(login_id: str, password: str) -> dict[str, object]:
    normalized_login_id = login_id.strip()
    trace_payload = {"login_id": normalized_login_id}
    link_cs_auto_trace(
        trace_payload,
        user_id=normalized_login_id,
        tags=["auth"],
        input_payload={"login_id": normalized_login_id},
    )
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
                result = {"authenticated": False, "reason": "invalid_credentials"}
                link_cs_auto_trace({**trace_payload, **result}, user_id=normalized_login_id, tags=["auth"], output_payload=result)
                return result

            if admin_user["status"] != "active":
                result = {"authenticated": False, "reason": "inactive_operator"}
                link_cs_auto_trace({**trace_payload, **result}, user_id=normalized_login_id, tags=["auth"], output_payload=result)
                return result

            password_hash = str(admin_user["password_hash"])
            if not password_hash.startswith(("$2a$", "$2b$", "$2y$")) or len(password_hash) != 60:
                result = {"authenticated": False, "reason": "invalid_credentials"}
                link_cs_auto_trace({**trace_payload, **result}, user_id=normalized_login_id, tags=["auth"], output_payload=result)
                return result

            password_matches = bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
            if not password_matches:
                result = {"authenticated": False, "reason": "invalid_credentials"}
                link_cs_auto_trace({**trace_payload, **result}, user_id=normalized_login_id, tags=["auth"], output_payload=result)
                return result

            cur.execute(
                """
                UPDATE admin_users
                SET last_login_at = CURRENT_TIMESTAMP
                WHERE admin_id = %s
                """,
                (admin_user["admin_id"],),
            )

    result = {
        "authenticated": True,
        "admin_id": admin_user["admin_id"],
        "login_id": admin_user["login_id"],
        "display_name": admin_user["display_name"],
        "role": admin_user["role"],
        "status": admin_user["status"],
    }
    link_cs_auto_trace(
        {**trace_payload, **result},
        user_id=admin_user["admin_id"],
        tags=["auth"],
        output_payload={
            "authenticated": True,
            "admin_id": admin_user["admin_id"],
            "role": admin_user["role"],
            "status": admin_user["status"],
        },
    )
    return result


@observe_if_enabled(name="cs_auto_create_admin_session", as_type="tool", tags=["cs-auto", "auth"])
def create_admin_session(admin_user: dict[str, object]) -> dict[str, object]:
    link_cs_auto_trace(
        admin_user,
        user_id=admin_user.get("admin_id"),
        tags=["auth"],
        input_payload={"admin_id": admin_user.get("admin_id"), "login_id": admin_user.get("login_id")},
    )
    session_id = uuid.uuid4().hex
    result = {
        "session_id": session_id,
        "admin_id": admin_user["admin_id"],
        "login_id": admin_user["login_id"],
        "display_name": admin_user["display_name"],
        "role": admin_user["role"],
    }
    link_cs_auto_trace(
        {**admin_user, **result},
        user_id=admin_user.get("admin_id"),
        session_id=session_id,
        tags=["auth"],
        output_payload={"session_id": session_id, "admin_id": admin_user["admin_id"]},
    )
    return result


@observe_if_enabled(name="cs_auto_revoke_admin_session", as_type="tool", tags=["cs-auto", "auth"])
def revoke_admin_session(session_id: str | None, admin_id: int | None = None) -> dict[str, object]:
    trace_payload = {"session_id": session_id, "admin_id": admin_id}
    link_cs_auto_trace(trace_payload, user_id=admin_id, session_id=session_id, tags=["auth"], input_payload=trace_payload)
    result = {"revoked": True, "session_id": session_id, "admin_id": admin_id}
    link_cs_auto_trace({**trace_payload, **result}, user_id=admin_id, session_id=session_id, tags=["auth"], output_payload=result)
    return result
