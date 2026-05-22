# Dashboard API Spec

이 문서는 `docs/dashboard/prd.md`와 `docs/dashboard/metrics.md`를 기준으로
Dashboard FastAPI가 제공해야 하는 읽기 전용 API 계약을 정의한다.

Dashboard API는 `src/dashboard/api/main.py`에서 제공하며, `/summary/*`는
`src/dashboard/workflow`의 LangGraph workflow를 통해 PostgreSQL 집계와 계산을 수행한다.
`/tickets`와 `/tickets/{ticket_id}`는 화면 탐색과 상세 확인에 필요한 원천 데이터를
실제 DB 테이블명과 컬럼명 기준으로 반환한다.

## 공통 원칙

- 모든 endpoint는 읽기 전용이다.
- 기본 조회 기간은 최근 30일이며, `days` 허용 범위는 1일부터 365일까지다.
- 기간 필터 기준은 `qa_ticket.inquiry_created_at >= window_start`이다.
- `window_start = now - days`로 계산한다.
- 오늘 접수 기준은 `CURRENT_DATE <= inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'`이다.
- 목록 기본 `limit`은 50, 최대 `limit`은 200이다.
- 비율 계산의 분모가 0이면 API는 `null` 또는 `0.0`을 반환하고, Streamlit은 `-`로 표시한다.
- 최신 레코드는 timestamp 내림차순, PK 내림차순으로 1건을 선택한다.
- 사용자 입력값은 SQL 문자열에 직접 연결하지 않고 검증된 파라미터로 바인딩한다.
- 목록 응답에서는 `raw_query`, `email`, `uid`, `transaction_id`, `refund_reason` 같은 민감 정보를 기본 노출하지 않는다.

## 최신 레코드 선택 기준

| 대상 | 정렬 기준 |
| --- | --- |
| 최신 분석 | `ticket_analysis.analyzed_at DESC NULLS LAST, ticket_analysis.analysis_id DESC` |
| 최신 초안 | `answer_draft.created_at DESC NULLS LAST, answer_draft.draft_id DESC` |
| 최신 Safety | `safety_results.checked_at DESC NULLS LAST, safety_results.safety_id DESC` |
| 최신 최종 답변 | `final_response.created_at DESC NULLS LAST, final_response.response_id DESC` |
| 최신 알림 | `notification_logs.sent_at DESC NULLS LAST, notification_logs.notification_id DESC` |

## Endpoints

### `GET /health`

Dashboard API와 DB 연결 상태를 확인한다.

Response:

```json
{
  "status": "ok",
  "database": "ok",
  "checked_at": "2026-05-22T00:00:00Z"
}
```

`database` 확인을 생략하는 구현에서는 최소 `{ "status": "ok" }`를 반환할 수 있다.

### `GET /summary/overview`

운영 현황 화면에 필요한 문의 처리 KPI, 분포, 최근 문의 목록을 반환한다.

Query params:

| Name | Type | Required | Default | Rule |
| --- | --- | --- | --- | --- |
| `days` | integer | no | `30` | `1 <= days <= 365` |

Response fields:

| Field | Description | Source |
| --- | --- | --- |
| `window` | `days`, `window_start`, `window_end` | API/workflow |
| `ticket_counts` | 전체 문의, pending, closed, 오늘 접수, 오래 대기 | `qa_ticket` |
| `response_metrics` | 답변 티켓 수, 답변율, 평균 답변 지연 분 | `qa_ticket`, `final_response` |
| `coverage_metrics` | 분석 커버리지, 초안 커버리지, 초안 티켓 수 | `ticket_analysis`, `answer_draft` |
| `source_distribution` | 접수 채널별 건수 | `qa_ticket.source_type` |
| `status_distribution` | 문의 상태별 건수 | `qa_ticket.status` |
| `routing_distribution` | 최신 분석의 라우팅 대상별 건수 | `ticket_analysis.routing_target` |
| `old_pending_count` | threshold를 넘긴 미종료 pending 건수 | `qa_ticket` |
| `recent_tickets` | 최근 문의 목록, 기본 50건 | `qa_ticket`와 최신 분석/초안/최종 답변 |

### `GET /summary/risk`

리스크 분석 화면에 필요한 위험도, 감성, safety 점수, 고위험 후보를 반환한다.

Query params:

| Name | Type | Required | Default | Rule |
| --- | --- | --- | --- | --- |
| `days` | integer | no | `30` | `1 <= days <= 365` |

Response fields:

| Field | Description | Source |
| --- | --- | --- |
| `window` | `days`, `window_start`, `window_end` | API/workflow |
| `analysis_risk_distribution` | 최신 `ticket_analysis.risk_level` 분포 | `ticket_analysis` |
| `sentiment_distribution` | 최신 분석 감성 분포 | `ticket_analysis.sentiment` |
| `insight_risk_distribution` | 인사이트 위험도 분포 | `insight.risk_level` |
| `pattern_risk_distribution` | 패턴 위험도 분포 | `insight.pattern_risk_level` |
| `safety_score_summary` | 평균 hallucination/toxicity/policy/factuality 점수 | `safety_results` |
| `safety_alerts` | 평균 점수 threshold 위반 여부 | `safety_results`, metrics threshold |
| `high_risk_tickets` | HIGH/critical 또는 `urgent_alert` 문의 | `qa_ticket`, `ticket_analysis`, `insight` |
| `safety_breach_candidates` | 개별 초안 safety threshold 위반 후보 | `answer_draft`, `safety_results` |

Safety threshold:

| Alert | Rule |
| --- | --- |
| 높은 환각 | `avg_hallucination_score >= 0.7` |
| 높은 유해성 | `avg_toxicity_score >= 0.7` |
| 높은 정책 위반 | `avg_policy_violation_score >= 0.7` |
| 낮은 사실성 | `avg_factuality_score <= 0.3` |

개별 safety breach 후보 기준:

```text
factuality_score <= 0.3
OR hallucination_score >= 0.7
OR policy_violation_score >= 0.7
OR toxicity_score >= 0.7
```

### `GET /summary/quality`

답변 품질 화면에 필요한 초안, 근거, safety, 최종 답변, 알림 상태를 반환한다.

Query params:

| Name | Type | Required | Default | Rule |
| --- | --- | --- | --- | --- |
| `days` | integer | no | `30` | `1 <= days <= 365` |

Response fields:

| Field | Description | Source |
| --- | --- | --- |
| `window` | `days`, `window_start`, `window_end` | API/workflow |
| `draft_summary` | 초안 수, 초안 티켓 수, 초안 커버리지 | `qa_ticket`, `answer_draft` |
| `evidence_summary` | 근거 연결 초안 수, 근거 첨부율, 평균 관련도/순위 | `answer_draft`, `evidence_docs` |
| `safety_summary` | safety 검사 수와 평균 점수 | `safety_results` |
| `final_response_summary` | 최종 답변 수, 최종 답변율, 평균 최종 지연 분 | `qa_ticket`, `final_response` |
| `notification_summary` | 알림 상태 분포 | `notification_logs.status` |
| `quality_candidates` | 낮은 사실성 또는 높은 환각 점수 초안 | `answer_draft`, `safety_results` |
| `notification_failures` | 실패/오류 알림 목록 | `notification_logs` |

품질 threshold:

| Alert | Rule |
| --- | --- |
| 낮은 답변율 | `response_rate < 0.7` |
| 낮은 초안 커버리지 | `draft_coverage_rate < 0.7` |
| 낮은 근거 첨부율 | `evidence_attachment_rate < 0.8` |

### `GET /summary/all`

통합 화면 또는 초기 로딩에 필요한 전체 요약을 한 번에 반환한다.

Query params:

| Name | Type | Required | Default | Rule |
| --- | --- | --- | --- | --- |
| `days` | integer | no | `30` | `1 <= days <= 365` |

Response fields:

| Field | Description |
| --- | --- |
| `overview` | `GET /summary/overview`와 동일한 구조 |
| `risk` | `GET /summary/risk`와 동일한 구조 |
| `quality` | `GET /summary/quality`와 동일한 구조 |

### `GET /tickets`

문의 목록 화면과 최근 문의 테이블에 필요한 행을 반환한다.

Query params:

| Name | Type | Required | Default | Rule |
| --- | --- | --- | --- | --- |
| `limit` | integer | no | `50` | `1 <= limit <= 200` |
| `status` | string | no | none | `qa_ticket.status` exact match |
| `risk_level` | string | no | none | 최신 `ticket_analysis.risk_level` exact match |
| `routing_target` | string | no | none | 최신 `ticket_analysis.routing_target` exact match |
| `source_type` | string | no | none | `qa_ticket.source_type` exact match |
| `days` | integer | no | `30` | `1 <= days <= 365` |

Response:

```json
{
  "items": [
    {
      "ticket_id": 1,
      "title": "문의 제목",
      "status": "pending",
      "source_type": "community",
      "nickname": "masked-user",
      "category": "payment",
      "risk_level": "high",
      "sentiment": "negative",
      "routing_target": "human_review",
      "latest_analysis_id": 10,
      "latest_draft_id": 20,
      "latest_response_id": 30,
      "inquiry_created_at": "2026-05-22T09:00:00"
    }
  ],
  "limit": 50,
  "count": 1
}
```

Required item fields:

| Field | Source |
| --- | --- |
| `ticket_id`, `title`, `status`, `source_type`, `inquiry_created_at` | `qa_ticket` |
| `nickname` | `community_users.nickname`, role-based masking allowed |
| `category`, `risk_level`, `sentiment`, `routing_target`, `latest_analysis_id` | latest `ticket_analysis` |
| `latest_draft_id` | latest `answer_draft` |
| `latest_response_id` | latest `final_response` |

### `GET /tickets/{ticket_id}`

특정 문의의 처리 맥락 전체를 반환한다.

Path params:

| Name | Type | Rule |
| --- | --- | --- |
| `ticket_id` | integer | existing `qa_ticket.ticket_id` |

Response fields:

| Field | Description | Source |
| --- | --- | --- |
| `ticket` | 문의 기본 정보. 상세 권한에서만 `raw_query` 표시 | `qa_ticket` |
| `account` | 사용자/게임 계정 요약. `email`, `uid`는 role-based masking | `community_users`, `game_accounts` |
| `analyses` | 분석 이력 전체 또는 최신 우선 정렬 | `ticket_analysis` |
| `drafts` | 초안 이력 | `answer_draft` |
| `evidence_docs` | 초안별 근거 문서 | `evidence_docs`, `documents`, `documents_chunks` |
| `safety_results` | 초안별 safety 검사 이력 | `safety_results` |
| `final_responses` | 최종 답변 이력 | `final_response` |
| `notifications` | Slack/Discord 등 알림 발송 이력 | `notification_logs` |
| `voc_feedback` | VOC 유형, 감성, 토픽 키워드 | `voc_feedback` |
| `operation_logs` | 결제, 환불, 아이템 지급, 가챠 맥락 | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` |

`operation_logs` 연결 기준:

| Context | Join rule |
| --- | --- |
| 결제 | `qa_ticket.account_id = payments.account_id` |
| 환불 | `payments.payment_id = refunds.payment_id` |
| 아이템 지급 | `qa_ticket.account_id = item_delivery_logs.account_id`, optional `payment_id` |
| 가챠 | `qa_ticket.account_id = gacha_logs.account_id` |

## Error Response

공통 오류 응답은 프론트엔드가 endpoint와 원인을 표시할 수 있도록 다음 구조를 사용한다.

```json
{
  "error": {
    "code": "invalid_parameter",
    "message": "days must be between 1 and 365",
    "endpoint": "/summary/overview",
    "details": {
      "parameter": "days"
    }
  }
}
```

## Observability

- API 호출 실패와 DB 조회 실패는 `failed_queries`, `admin_event_logs` 또는 애플리케이션 로그와 연계한다.
- 알림 발송 결과는 `notification_logs.channel`, `status`, `message`, `error_message`, `error_category`, `sent_at`으로 추적한다.
- `/health` 실패 또는 DB 연결 실패는 `dashboard_api_down` Slack 알림 조건이 될 수 있다.
