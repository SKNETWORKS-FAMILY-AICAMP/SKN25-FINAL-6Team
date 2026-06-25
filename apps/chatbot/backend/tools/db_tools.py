from __future__ import annotations

import json

from langchain_core.tools import tool


# Agent가 추론 중 직접 조회할 수 있는 DB read만 LangChain tool로 노출한다.
# 티켓/초안/safety/최종응답 저장은 workflow 노드에서 repository를 직접 호출한다.
def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# 버그 agent가 아이템 미지급 문의를 검토할 때 로그인 사용자 소유 계정의 지급 로그만 조회한다.
@tool(parse_docstring=True)
def read_item_delivery_logs(user_id: int, account_id: int) -> str:
    """Read item delivery log records for an account owned by the logged-in user.

    Args:
        user_id: Logged-in community user ID. This is the ownership boundary.
        account_id: Game account ID to look up delivery logs for, only if it belongs to user_id.
    """
    from repository.operation_log_repository import read_item_delivery_logs_by_account

    return _json(read_item_delivery_logs_by_account(user_id=user_id, account_id=account_id))


# 버그 agent가 가챠/뽑기 결과 문의를 검토할 때 로그인 사용자 소유 계정의 뽑기 로그만 조회한다.
@tool(parse_docstring=True)
def read_gacha_logs(user_id: int, account_id: int) -> str:
    """Read gacha pull log records for an account owned by the logged-in user.

    Args:
        user_id: Logged-in community user ID. This is the ownership boundary.
        account_id: Game account ID to look up gacha logs, only if it belongs to user_id.
    """
    from repository.operation_log_repository import read_gacha_logs_by_account

    return _json(read_gacha_logs_by_account(user_id=user_id, account_id=account_id))


# payment agent가 결제/환불/아이템 지급/가챠 로그를 사용자 소유 범위 안에서 한 번에 모은다.
@tool(parse_docstring=True)
def collect_user_payment_context(
    user_id: int,
    account_id: int | None = None,
    query_text: str | None = None,
) -> str:
    """Read payment, refund, item delivery, and gacha records owned by the logged-in user.

    Args:
        user_id: Logged-in community user ID. This is the ownership boundary.
        account_id: Optional game account ID to narrow the lookup, only if it belongs to user_id.
        query_text: Optional user question text used to prioritize matching payment records.
    """
    from repository.operation_log_repository import collect_payment_context_by_user

    return _json(collect_payment_context_by_user(user_id=user_id, account_id=account_id, query_text=query_text))
