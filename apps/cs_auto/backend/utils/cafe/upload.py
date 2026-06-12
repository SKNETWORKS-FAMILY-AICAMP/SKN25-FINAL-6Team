"""
프론트엔드에서 운영자가 답변을 승인할 시, 특정 네이버 카페의 게시물에 댓글을 달 수 있도록 하는 함수를 설계.
이 함수에서 api 포인트를 만들어내, 프론트에 전달할 수 있도록 한다.
"""

from __future__ import annotations

import os

from psycopg.rows import dict_row
from common.db.connection import db_connection


def build_cafe_comment_payload(ticket_id: int, response_id: int) -> dict[str, object]:
    """
    final_response에 저장된 최종 답변을 네이버 카페 댓글 업로드 payload로 만든다.

    예상 내용:
    - qa_ticket.ticket_id로 원문 게시물 출처와 source_type이 naver_cafe인지 확인한다.
    - final_response.response_id로 final_text를 조회한다.
    - 카페 게시글 URL, 댓글 본문, 운영자 식별 정보, 재시도 가능 여부를 정리한다.
    """

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.source_type,
                    t.title,
                    t.raw_query,
                    t.session_id,
                    fr.response_id,
                    fr.final_text,
                    fr.created_at
                FROM qa_ticket t
                JOIN final_response fr ON fr.ticket_id = t.ticket_id
                WHERE t.ticket_id = %s
                  AND fr.response_id = %s
                """,
                (ticket_id, response_id),
            )
            row = cur.fetchone()

    if row is None:
        return {
            "ready": False,
            "ticket_id": ticket_id,
            "response_id": response_id,
            "reason": "final_response_not_found",
        }

    return {
        "ready": row["source_type"] == "naver_cafe",
        "ticket_id": row["ticket_id"],
        "response_id": row["response_id"],
        "source_type": row["source_type"],
        "post_reference": row["session_id"],
        "title": row["title"],
        "comment_text": row["final_text"],
        "created_at": row["created_at"],
    }


def upload_comment_to_naver_cafe(payload: dict[str, object]) -> dict[str, object]:
    """
    네이버 카페 게시물에 최종 답변 댓글을 업로드한다.

    예상 내용:
    - api.main.upload_final_answer_to_cafe에서 호출한다.
    - 인증 쿠키, 토큰, 카페 게시글 URL 등 외부 연동 정보는 환경 변수 또는 Secret Manager에서 읽는다.
    - 업로드 성공 시 댓글 식별자, 업로드 시각, 응답 상태를 반환한다.
    - 업로드 실패 시 final_response와 qa_ticket 상태를 되돌리지 않고 재시도 가능한 실패 정보를 반환한다.
    """

    endpoint = os.environ.get("NAVER_CAFE_COMMENT_ENDPOINT")
    if not payload.get("ready"):
        return {
            "status": "skipped",
            "reason": payload.get("reason") or "unsupported_source_type",
            "payload": payload,
        }

    if not endpoint:
        return {
            "status": "prepared",
            "reason": "NAVER_CAFE_COMMENT_ENDPOINT is not configured",
            "payload": payload,
        }

    return {
        "status": "prepared",
        "endpoint": endpoint,
        "payload": payload,
    }


def record_cafe_upload_result(
    ticket_id: int,
    response_id: int,
    upload_result: dict[str, object],
) -> dict[str, object]:
    """
    네이버 카페 댓글 업로드 결과를 운영 로그에 기록한다.

    예상 내용:
    - 성공 또는 실패 결과를 notification_logs에 남긴다.
    - ticket_id, response_id, 업로드 대상, status, error_message를 추적 가능하게 저장한다.
    - 프론트엔드가 업로드 완료 또는 재시도 필요 상태를 표시할 수 있는 payload를 반환한다.
    """

    status = str(upload_result.get("status") or "unknown")
    error_message = upload_result.get("reason")
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO notification_logs (
                    ticket_id,
                    channel,
                    status,
                    message,
                    error_message,
                    error_category
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING notification_id, sent_at
                """,
                (
                    ticket_id,
                    "naver_cafe",
                    status,
                    str(upload_result.get("payload", {}).get("comment_text") or ""),
                    error_message,
                    "external_endpoint" if error_message else None,
                ),
            )
            notification = cur.fetchone()
            # admin_event_logs 테이블 사용 중단으로 카페 업로드 이벤트 적재는 비활성화한다.
            # cur.execute(
            #     """
            #     INSERT INTO admin_event_logs (
            #         ticket_id,
            #         node_name,
            #         event_type,
            #         status,
            #         metadata
            #     )
            #     VALUES (%s, %s, %s, %s, %s)
            #     """,
            #     (
            #         ticket_id,
            #         "cs_auto_cafe_upload",
            #         "cafe_comment_upload",
            #         status,
            #         Json({"response_id": response_id, "upload_result": upload_result}),
            #     ),
            # )

    return {
        "ticket_id": ticket_id,
        "response_id": response_id,
        "status": status,
        "notification_id": notification["notification_id"] if notification else None,
        "sent_at": notification["sent_at"] if notification else None,
        "upload_result": upload_result,
    }
