# Operation API Spec

Base URL: `http://127.0.0.1:8000`

## GET /health

API 상태를 확인합니다.

Response:

```json
{
  "status": "ok"
}
```

## GET /tickets/today

운영자가 오늘 우선 확인해야 할 문의 목록을 조회합니다. 날짜 기준은 DB 서버의 `CURRENT_DATE`이며 `qa_ticket.inquiry_created_at`을 기준으로 필터링합니다.

Query parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `status` | string | no | `pending` | 티켓 상태 필터. 전체 상태를 보려면 생략하거나 null로 호출 |
| `limit` | integer | no | 100 | 1 이상 200 이하 |

Response fields:

| Field | Description |
| --- | --- |
| `ticket_id` | 티켓 ID |
| `user_id` | 사용자 ID |
| `account_id` | 게임 계정 ID |
| `title` | 문의 제목 |
| `source_type` | 문의 채널 |
| `status` | 티켓 상태 |
| `inquiry_created_at` | 문의 생성 시각 |
| `nickname` | 사용자 닉네임 |
| `draft_id` | 최신 초안 ID |
| `draft_created_at` | 최신 초안 생성 시각 |
| `risk_level` | 최신 분석 위험도 |
| `routing_target` | 최신 분석 목표 route |

## GET /tickets

문의 목록과 최신 분석/초안 요약을 조회합니다.

Query parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `status` | string | no | null | `qa_ticket.status` 필터 |
| `limit` | integer | no | 50 | 1 이상 200 이하 |
| `today_only` | boolean | no | false | true이면 오늘 접수된 문의만 조회 |

`GET /tickets/today`는 `GET /tickets?today_only=true&status=pending`과 같은 목적의 운영자 친화 API입니다.

## GET /tickets/{ticket_id}

문의 상세와 관련 검수 데이터를 조회합니다.

Response top-level fields:

| Field | Description |
| --- | --- |
| `ticket` | 티켓, 사용자, 게임 계정 상세 |
| `analyses` | `ticket_analysis` 목록 |
| `drafts` | `answer_draft` 목록 |
| `evidence_docs` | 초안별 근거 문서 목록 |
| `safety_results` | 초안별 안전성 검수 결과 |
| `final_responses` | 최종 답변 목록 |
| `notifications` | 긴급 알림 목록 |
| `review_logs` | 운영자 검수 이벤트 로그 |

## PATCH /drafts/{draft_id}

운영자가 답변 초안을 수정 저장합니다. 최종 발행은 하지 않습니다.

Request:

```json
{
  "draft_text": "수정된 답변 초안",
  "reviewer_id": "operator01"
}
```

Response:

```json
{
  "ticket_id": 1001,
  "draft_id": 1,
  "decision": "edited",
  "status": "draft_edited",
  "response_id": null
}
```

Side effects:

- `answer_draft.draft_text` 업데이트
- `admin_event_logs`에 `decision=edited` 저장

## POST /drafts/{draft_id}/approve

운영자가 초안을 승인하고 최종 답변으로 발행합니다.

Request:

```json
{
  "final_text": "최종 답변",
  "reviewer_id": "operator01"
}
```

`final_text`가 없으면 현재 `answer_draft.draft_text`가 최종 답변으로 사용됩니다.

Response:

```json
{
  "ticket_id": 1001,
  "draft_id": 1,
  "decision": "approved",
  "status": "closed",
  "response_id": 10
}
```

Side effects:

- `final_response` 생성
- `qa_ticket.status = closed`
- `admin_event_logs`에 `decision=approved` 저장

## POST /drafts/{draft_id}/reject

운영자가 초안을 반려합니다.

Request:

```json
{
  "reason": "근거 문서가 부족합니다.",
  "reviewer_id": "operator01"
}
```

Response:

```json
{
  "ticket_id": 1001,
  "draft_id": 1,
  "decision": "rejected",
  "status": "pending",
  "response_id": null
}
```

Side effects:

- `qa_ticket.status = pending`
- `admin_event_logs`에 `decision=rejected`와 반려 사유 저장
