from __future__ import annotations

from typing import Any

from chatbot.observability.langfuse import build_login_trace_metadata
from chatbot.observability.logger import log_event
from chatbot.repository.account_repository import read_server_regions, verify_user_login
from common.observability.langfuse import link_current_trace, observe_if_enabled

DEFAULT_SERVER_REGIONS = ["ASIA", "KR", "EU", "NA"]


def get_server_regions() -> list[str]:
    result = read_server_regions()
    if result.get("status") != "ok":
        return DEFAULT_SERVER_REGIONS

    db_regions = [
        str(row["server_region"]).strip()
        for row in result.get("data", [])
        if row.get("server_region") and str(row["server_region"]).strip()
    ]
    regions = []
    for region in [*DEFAULT_SERVER_REGIONS, *db_regions]:
        if region not in regions:
            regions.append(region)
    return regions or DEFAULT_SERVER_REGIONS


def _login_trace_input(email: str, server_region: str) -> dict[str, Any]:
    return {
        "email": email,
        "server_region": server_region,
    }


def _login_trace_output(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "login_success": response.get("login_success"),
        "user_id": response.get("user_id"),
        "account_id": response.get("account_id"),
        "game_id": response.get("game_id"),
        "email": response.get("email"),
        "server_region": response.get("server_region"),
        "message": response.get("message"),
    }


@observe_if_enabled(
    name="game_account_login",
    as_type="chain",
    tags=["chatbot", "feature:login"],
)
def login_with_credentials(email: str, password: str, server_region: str) -> dict[str, Any]:
    normalized_email = email.strip()
    normalized_region = server_region.strip()
    link_current_trace(
        user_id=normalized_email or None,
        tags=["chatbot", "feature:login"],
        metadata=build_login_trace_metadata(
            {
                "email": normalized_email,
                "server_region": normalized_region,
            }
        ),
        input_payload=_login_trace_input(normalized_email, normalized_region),
    )

    if not normalized_email or not password or not normalized_region:
        response = {
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "game_id": "",
            "email": normalized_email,
            "server_region": normalized_region,
            "message": "이메일, 비밀번호, 서버를 모두 입력해 주세요.",
        }
        _log_login_result(response)
        link_current_trace(
            user_id=normalized_email or None,
            tags=["chatbot", "feature:login"],
            metadata=build_login_trace_metadata(response),
            output_payload=_login_trace_output(response),
        )
        return response

    result = verify_user_login(normalized_email, password, normalized_region)
    if result.get("status") != "ok":
        response = {
            "login_success": False,
            "user_id": None,
            "account_id": None,
            "game_id": "",
            "email": normalized_email,
            "server_region": normalized_region,
            "message": "계정 조회 중 오류가 발생했습니다. DB 연결과 환경변수를 확인해 주세요.",
        }
        _log_login_result(response, db_status=result.get("status"), error=result.get("error"))
        link_current_trace(
            user_id=normalized_email or None,
            tags=["chatbot", "feature:login"],
            metadata=build_login_trace_metadata(
                response,
                db_status=result.get("status"),
                error=result.get("error"),
            ),
            output_payload=_login_trace_output(response),
        )
        return response

    response = {
        "login_success": bool(result.get("login_success")),
        "user_id": result.get("user_id"),
        "account_id": result.get("account_id"),
        "game_id": result.get("game_id") or result.get("uid") or "",
        "email": result.get("email") or normalized_email,
        "server_region": result.get("server_region") or normalized_region,
        "nickname": result.get("nickname"),
        "message": result.get("message") or "로그인 성공",
    }
    _log_login_result(response, db_status=result.get("status"))
    link_current_trace(
        user_id=response.get("user_id") or normalized_email or None,
        tags=["chatbot", "feature:login"],
        metadata=build_login_trace_metadata(response, db_status=result.get("status")),
        output_payload=_login_trace_output(response),
    )
    return response


def _log_login_result(login_result: dict[str, Any], **extra_metadata: Any) -> None:
    log_event(
        "game_account_login_completed",
        status="ok" if login_result.get("login_success") else "failed",
        metadata={
            "login_success": login_result.get("login_success"),
            "user_id": login_result.get("user_id"),
            "account_id": login_result.get("account_id"),
            "game_id": login_result.get("game_id"),
            "email": login_result.get("email"),
            "server_region": login_result.get("server_region"),
            **{key: value for key, value in extra_metadata.items() if value is not None},
        },
    )
