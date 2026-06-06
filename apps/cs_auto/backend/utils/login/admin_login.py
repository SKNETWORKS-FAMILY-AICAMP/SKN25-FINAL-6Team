"""
프론트엔드에서 로그인하는 운영자가 실제로 운영자가 맞는지 admin_users 테이블 기준으로 확인하는 함수. 
이 함수에서 api 포인트를 만들어내서 프론트에 전달한다.
"""


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

    pass


def create_admin_session(admin_user: dict[str, object]) -> dict[str, object]:
    """
    로그인 성공 후 프론트엔드가 사용할 운영자 세션 정보를 만든다.

    예상 내용:
    - admin_id와 role을 기준으로 API 접근 범위를 정한다.
    - 세션 토큰 또는 쿠키 기반 인증 정보를 발급한다.
    - last_login_at 갱신과 admin_event_logs 로그인 이벤트 기록에 필요한 값을 준비한다.
    """

    pass


def revoke_admin_session(session_id: str | None, admin_id: int | None = None) -> dict[str, object]:
    """
    로그아웃 요청 시 운영자 세션을 무효화한다.

    예상 내용:
    - api.main.api_logout_operator에서 호출한다.
    - 세션 저장소나 토큰 블랙리스트 정책에 따라 현재 로그인 상태를 종료한다.
    - admin_event_logs에 logout 이벤트를 기록할 수 있는 결과를 반환한다.
    """

    pass
