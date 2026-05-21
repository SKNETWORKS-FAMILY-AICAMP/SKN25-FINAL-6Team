# Dashboard API Spec

`src/dashboard/api/main.py`가 제공하는 읽기 전용 API 규격이다. 응답은 JSON이며, Streamlit 프론트엔드는 이 API만 호출한다.

## Endpoints

### `GET /health`

Health check.

Response:

```json
{ "status": "ok" }
```

### `GET /summary/overview`

운영 현황 요약.

Query params:

- `days` optional, default `30`

Response fields:

- `ticket_counts`
- `response_metrics`
- `source_distribution`
- `status_distribution`
- `routing_distribution`
- `recent_tickets`

### `GET /summary/risk`

리스크 분석 요약.

Query params:

- `days` optional, default `30`

Response fields:

- `analysis_risk_distribution`
- `sentiment_distribution`
- `insight_risk_distribution`
- `pattern_risk_distribution`
- `safety_score_summary`
- `high_risk_tickets`

### `GET /summary/quality`

응답 품질 요약.

Query params:

- `days` optional, default `30`

Response fields:

- `draft_summary`
- `evidence_summary`
- `safety_summary`
- `final_response_summary`
- `notification_summary`
- `quality_candidates`

### `GET /tickets`

최근 티켓 목록.

Query params:

- `limit` optional, default `50`, min `1`, max `200`
- `status` optional

Response: list of ticket rows joined with latest analysis and draft metadata.

### `GET /tickets/{ticket_id}`

티켓 상세.

Response fields:

- `ticket`
- `analyses`
- `drafts`
- `evidence_docs`
- `safety_results`
- `final_responses`
- `notifications`

## Notes

- 날짜 필터는 `qa_ticket.inquiry_created_at` 기준이다.
- 최신 값이 필요한 테이블은 티켓 단위로 최신 레코드를 선택한다.
- 모든 숫자는 프론트엔드가 바로 렌더링할 수 있도록 API에서 집계한다.

