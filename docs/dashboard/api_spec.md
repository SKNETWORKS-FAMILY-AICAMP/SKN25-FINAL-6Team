# Dashboard API Spec

`src/dashboard/api/main.py`는 FastAPI 기반 읽기 전용 API다. 요약 endpoint는 `src/dashboard/workflow`의 LangGraph를 실행하고, 목록/상세 endpoint는 화면 탐색에 필요한 원천 데이터를 반환한다.

## Endpoints

### `GET /health`

Health check.

```json
{ "status": "ok" }
```

### `GET /summary/overview`

운영 현황 요약.

Query params:

- `days`: optional, default `30`, min `1`, max `365`

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

- `days`: optional, default `30`, min `1`, max `365`

Response fields:

- `analysis_risk_distribution`
- `sentiment_distribution`
- `insight_risk_distribution`
- `pattern_risk_distribution`
- `safety_score_summary`
- `safety_alerts`
- `high_risk_tickets`

### `GET /summary/quality`

응답 품질 요약.

Query params:

- `days`: optional, default `30`, min `1`, max `365`

Response fields:

- `ticket_summary`
- `draft_summary`
- `evidence_summary`
- `safety_summary`
- `final_response_summary`
- `notification_summary`
- `quality_candidates`
- `coverage_metrics`

### `GET /summary/all`

운영 현황, 리스크 분석, 응답 품질을 한 번에 반환한다.

### `GET /tickets`

최근 문의 목록.

Query params:

- `limit`: optional, default `50`, min `1`, max `200`
- `status`: optional

Response: ticket rows joined with latest analysis, draft, and final response metadata.

### `GET /tickets/{ticket_id}`

티켓 상세 조회.

Response fields:

- `ticket`
- `analyses`
- `drafts`
- `evidence_docs`
- `safety_results`
- `final_responses`
- `notifications`
- `voc_feedback`

## Notes

- 날짜 필터는 `qa_ticket.inquiry_created_at` 기준이다.
- 최신 레코드는 티켓 단위 `LEFT JOIN LATERAL (...) ORDER BY timestamp DESC, id DESC LIMIT 1`로 선택한다.
- API 응답은 Streamlit에서 바로 렌더링할 수 있도록 숫자, 비율, 분포 배열을 포함한다.
