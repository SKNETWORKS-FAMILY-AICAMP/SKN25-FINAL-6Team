from __future__ import annotations

from typing import Any

from langsmith import traceable

from chatbot.observability.logger import log_event
from chatbot.repository.account_repository import read_server_regions, verify_user_login


def _login_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    # LangSmith trace에는 비밀번호 원문이 남지 않도록 입력을 마스킹한다.
    return {
        "email": inputs.get("email"),
        "server_region": inputs.get("server_region"),
        "password": "***",
    }


def _login_outputs(output: dict[str, Any]) -> dict[str, Any]:
    # 로그인 결과 trace에는 성공 여부와 계정 식별 정보만 남긴다.
    return {
        "login_success": output.get("login_success"),
        "user_id": output.get("user_id"),
        "account_id": output.get("account_id"),
        "game_id": output.get("game_id"),
        "email": output.get("email"),
        "server_region": output.get("server_region"),
        "message": output.get("message"),
    }


def get_server_regions() -> list[str]:
    # DB에서 서버 목록을 읽되, 실패하면 프론트가 깨지지 않도록 기본 서버를 반환한다.
    result = read_server_regions()
    if result.get("status") != "ok":
        return ["KR", "JP"]
    regions = [row["server_region"] for row in result.get("data", []) if row.get("server_region")]
    return regions or ["KR", "JP"]


@traceable(
    run_type="tool",
    name="game_account_login",
    tags=["chatbot", "login", "game_account"],
    process_inputs=_login_inputs,
    process_outputs=_login_outputs,
)
def login_with_credentials(email: str, password: str, server_region: str) -> dict[str, Any]:
    # 1단계: 입력값을 정리하고 필수값이 비어 있으면 DB 조회 전에 실패 응답을 만든다.
    normalized_email = email.strip()
    normalized_region = server_region.strip()
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
        return response

    # 2단계: account_repository에서 실제 계정/비밀번호/서버 매칭을 확인한다.
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
        return response

    # 3단계: 로그인 성공/실패 결과를 API 응답 스키마에 맞는 dict로 정리한다.
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
    return response


def _log_login_result(login_result: dict[str, Any], **extra_metadata: Any) -> None:
    # 로그인 성공/실패를 admin log와 LangSmith trace에서 추적할 수 있게 이벤트로 남긴다.
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
