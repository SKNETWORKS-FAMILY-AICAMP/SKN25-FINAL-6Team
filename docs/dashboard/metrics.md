# Dashboard Metrics

이 문서는 `docs/dashboard/prd.md`를 기준으로 운영 대시보드에서 계산해 운영자에게 보여줄 지표와 Slack 알림 조건을 정의한다.

모든 테이블과 컬럼은 `docs/DB/descriptions.md`의 실제 PostgreSQL `public` 스키마를 기준으로 한다. 대시보드는 원칙적으로 읽기 전용이며, 지표 계산은 PostgreSQL 조회와 `src/dashboard/workflow/nodes.py`의 compute 노드에서 수행한다.

## 공통 필터

- 조회 기간: `qa_ticket.inquiry_created_at >= window_start`
- `window_start = datetime.now() - timedelta(days=days)`
- 기본 `days = 30`, API 허용 범위는 1일부터 365일까지다.
- 오늘 기준: `CURRENT_DATE <= inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'`
- 비율 계산에서 분모가 0이면 `null` 또는 `0.0`으로 반환하고, 프론트엔드는 `-`로 표시한다.
- 티켓별 최신 분석/초안/검증/응답은 `analyzed_at`, `created_at`, `checked_at`, 각 PK의 내림차순으로 1건을 선택한다.

## 운영자에게 보여줄 핵심 계산

### 운영 현황

운영자는 문의 유입과 처리 backlog를 먼저 확인한다.

| Metric | Formula | Source | 화면 표시 |
| --- | --- | --- | --- |
| 전체 문의 | `COUNT(*)` | `qa_ticket` | KPI |
| 대기 문의 | `COUNT(*) FILTER (WHERE status = 'pending')` | `qa_ticket` | KPI, backlog |
| 종료 문의 | `COUNT(*) FILTER (WHERE status = 'closed')` | `qa_ticket` | KPI |
| 오늘 접수 | `COUNT(*) FILTER (WHERE inquiry_created_at >= CURRENT_DATE AND inquiry_created_at < CURRENT_DATE + INTERVAL '1 day')` | `qa_ticket` | KPI |
| 응답 티켓 수 | `COUNT(DISTINCT final_response.ticket_id)` | `final_response` | 보조 수치 |
| 응답률 | `responded_tickets / total_tickets` | `qa_ticket`, `final_response` | KPI 퍼센트 |
| 초안 티켓 수 | `COUNT(DISTINCT answer_draft.ticket_id)` | `answer_draft` | 보조 수치 |
| 초안 커버리지 | `draft_tickets / total_tickets` | `qa_ticket`, `answer_draft` | KPI 퍼센트 |
| 분석 티켓 수 | `COUNT(DISTINCT ticket_analysis.ticket_id)` | `ticket_analysis` | 보조 수치 |
| 분석 커버리지 | `analyzed_tickets / total_tickets` | `qa_ticket`, `ticket_analysis` | KPI 퍼센트 |
| 평균 응답 지연 | `AVG(EXTRACT(EPOCH FROM final_response.created_at - qa_ticket.inquiry_created_at) / 60)` | `qa_ticket`, `final_response` | 분 단위 KPI |
| 접수 채널 분포 | `COUNT(*) GROUP BY source_type` | `qa_ticket` | Bar chart |
| 상태 분포 | `COUNT(*) GROUP BY status` | `qa_ticket` | Bar chart |
| 라우팅 대상 분포 | 최신 `ticket_analysis.routing_target` 기준 `COUNT(*) GROUP BY routing_target` | `ticket_analysis` | Bar chart |

### 리스크 분석

리스크 담당자는 고위험 문의, 부정 감성, 안전성 점수 악화를 확인한다.

| Metric | Formula | Source | 화면 표시 |
| --- | --- | --- | --- |
| 분석 리스크 분포 | 최신 `ticket_analysis.risk_level` 기준 `COUNT(*) GROUP BY risk_level` | `ticket_analysis` | Bar chart |
| HIGH/critical 문의 수 | `COUNT(*) WHERE lower(risk_level) IN ('high', 'critical')` | `ticket_analysis` | KPI, table badge |
| 감성 분포 | 최신 `ticket_analysis.sentiment` 기준 `COUNT(*) GROUP BY sentiment` | `ticket_analysis` | Bar chart |
| 부정 감성 수 | `COUNT(*) WHERE lower(sentiment) IN ('negative', 'very_negative')` | `ticket_analysis`, `insight`, `voc_feedback` | KPI |
| 인사이트 리스크 분포 | `COUNT(*) GROUP BY insight.risk_level` | `insight` | Bar chart |
| 패턴 리스크 분포 | `COUNT(*) GROUP BY insight.pattern_risk_level` | `insight` | Bar chart |
| 평균 환각 점수 | `AVG(safety_results.hallucination_score)` | `safety_results` | Safety KPI |
| 평균 유해성 점수 | `AVG(safety_results.toxicity_score)` | `safety_results` | Safety KPI |
| 평균 정책 위반 점수 | `AVG(safety_results.policy_violation_score)` | `safety_results` | Safety KPI |
| 평균 사실성 점수 | `AVG(safety_results.factuality_score)` | `safety_results` | Safety KPI |
| 고위험 후보 | 최신 분석 또는 인사이트 패턴 리스크가 `high`, `critical`인 티켓 | `qa_ticket`, `ticket_analysis`, `insight` | 우선 검토 테이블 |
| 검증 미달 후보 | `factuality_score <= 0.3 OR hallucination_score >= 0.7 OR policy_violation_score >= 0.7 OR toxicity_score >= 0.7` | `answer_draft`, `safety_results` | 우선 검토 테이블 |

### 응답 품질

품질 관리자는 자동 생성 답변이 근거와 안전성 기준을 충족하는지 확인한다.

| Metric | Formula | Source | 화면 표시 |
| --- | --- | --- | --- |
| 초안 수 | `COUNT(DISTINCT answer_draft.draft_id)` | `answer_draft` | KPI |
| 초안 티켓률 | `draft_ticket_count / ticket_count` | `qa_ticket`, `answer_draft` | KPI 퍼센트 |
| 근거 연결 초안 | `COUNT(DISTINCT draft_id) WHERE EXISTS evidence_docs` | `answer_draft`, `evidence_docs` | KPI |
| 근거 첨부율 | `evidence_linked_drafts / draft_count` | `answer_draft`, `evidence_docs` | KPI 퍼센트 |
| 평균 근거 관련도 | `AVG(evidence_docs.relevance_score)` | `evidence_docs` | 점수 KPI |
| 평균 근거 순위 | `AVG(evidence_docs.retrieval_rank)` | `evidence_docs` | 보조 수치 |
| 최종 응답 수 | `COUNT(DISTINCT final_response.response_id)` | `final_response` | KPI |
| 최종 응답률 | `final_response_ticket_count / ticket_count` | `qa_ticket`, `final_response` | KPI 퍼센트 |
| 평균 최종 지연 | `AVG(EXTRACT(EPOCH FROM final_response.created_at - qa_ticket.inquiry_created_at) / 60)` | `qa_ticket`, `final_response` | 분 단위 KPI |
| 알림 상태 분포 | `COUNT(*) GROUP BY notification_logs.status` | `notification_logs` | Bar chart |
| 품질 점검 후보 | 낮은 `factuality_score`, 높은 `hallucination_score` 우선 정렬 | `answer_draft`, `safety_results` | Table |

### 검수 큐

운영자와 상담원은 자동 처리되지 못한 문의와 긴급 문의를 별도 큐로 확인한다.

| Metric | Formula | Source | 화면 표시 |
| --- | --- | --- | --- |
| 운영자 검토 대상 | `COUNT(*) WHERE status = 'human_review' OR latest.routing_target = 'human_review' OR latest.safety_action = 'human_review'` | `qa_ticket`, `ticket_analysis`, `safety_results` | KPI, table |
| 긴급 알림 대상 | `COUNT(*) WHERE latest.routing_target = 'urgent_alert' OR lower(latest.risk_level) IN ('high', 'critical')` | `ticket_analysis`, `insight` | KPI, table |
| 수동 처리 후보 | 결제/환불/미지급/가챠 category 중 검증 미달 또는 로그 불일치 후보 | `ticket_analysis`, `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` | Table |
| 미응답 장기 대기 | `COUNT(*) WHERE status <> 'closed' AND now() - inquiry_created_at > threshold` | `qa_ticket` | KPI, warning |

## 계산 기준 상세

### 최신 레코드 선택

티켓 목록과 상세에서 최신 분석, 최신 초안, 최신 검증, 최신 최종 응답을 붙일 때는 다음 우선순위를 사용한다.

| 대상 | 정렬 기준 |
| --- | --- |
| 최신 분석 | `ticket_analysis.analyzed_at DESC NULLS LAST, ticket_analysis.analysis_id DESC` |
| 최신 초안 | `answer_draft.created_at DESC NULLS LAST, answer_draft.draft_id DESC` |
| 최신 Safety | `safety_results.checked_at DESC NULLS LAST, safety_results.safety_id DESC` |
| 최신 최종 응답 | `final_response.created_at DESC NULLS LAST, final_response.response_id DESC` |
| 최신 알림 | `notification_logs.sent_at DESC NULLS LAST, notification_logs.notification_id DESC` |

### 결제/지급 이상 후보

결제, 환불, 미지급, 가챠 문의는 티켓의 `account_id`와 업무 로그를 함께 본다.

| 후보 | Rule | Source |
| --- | --- | --- |
| 결제 성공 후 미지급 | `payments.payment_status = 'success' AND item_delivery_logs.delivery_status IN ('fail', 'failed')` | `payments`, `item_delivery_logs` |
| 결제 성공 후 지급 로그 없음 | `payments.payment_status = 'success' AND NOT EXISTS item_delivery_logs WHERE payment_id = payments.payment_id` | `payments`, `item_delivery_logs` |
| 환불 장기 대기 | `refunds.refund_status IN ('requested', 'pending') AND now() - requested_at > INTERVAL '24 hours'` | `refunds` |
| 계정 상태 이상 | `game_accounts.account_status NOT IN ('active', 'normal') OR community_users.user_status NOT IN ('active', 'normal')` | `game_accounts`, `community_users` |

## Dashboard Alert Threshold

이 threshold는 대시보드 화면에서 `warning`, `danger`, badge를 표시하는 기준이다. Slack 알림 조건은 다음 섹션의 조건을 따른다.

| Alert | Rule | 표시 |
| --- | --- | --- |
| 높은 환각 | `avg_hallucination_score >= 0.7` | 리스크 화면 경고 |
| 높은 유해성 | `avg_toxicity_score >= 0.7` | 리스크 화면 경고 |
| 높은 정책 위반 | `avg_policy_violation_score >= 0.7` | 리스크 화면 경고 |
| 낮은 사실성 | `avg_factuality_score <= 0.3` | 리스크 화면 경고 |
| 응답률 저하 | `response_rate < 0.7` | 운영 현황 경고 |
| 초안 커버리지 저하 | `draft_coverage_rate < 0.7` | 응답 품질 경고 |
| 근거 첨부율 저하 | `evidence_attachment_rate < 0.8` | 응답 품질 경고 |
| 장기 대기 증가 | `old_pending_count >= 10` | 운영 현황 경고 |

## Slack 알림 조건

Slack 알림은 운영자가 즉시 확인해야 하는 상황에만 발송한다. 화면 경고만 필요한 일반 품질 저하는 대시보드에 표시하고, 기준을 연속으로 위반하거나 장애성 조건일 때 Slack으로 보낸다.

### 즉시 알림

| Alert Type | Trigger | Severity | Source | Slack 메시지 필드 |
| --- | --- | --- | --- | --- |
| `urgent_ticket_detected` | 최신 `ticket_analysis.routing_target = 'urgent_alert'` 또는 `lower(risk_level) IN ('high', 'critical')` | critical | `qa_ticket`, `ticket_analysis`, `insight` | `ticket_id`, `title`, `risk_level`, `routing_target`, `summary` |
| `safety_threshold_breach` | 개별 초안의 `hallucination_score >= 0.8 OR toxicity_score >= 0.8 OR policy_violation_score >= 0.8 OR factuality_score <= 0.2` | critical | `answer_draft`, `safety_results` | `ticket_id`, `draft_id`, 각 score, `safety_action`, `safety_reason` |
| `payment_delivery_mismatch` | 결제 성공 후 지급 실패 또는 지급 로그 없음 | critical | `payments`, `item_delivery_logs`, `qa_ticket` | `ticket_id`, `account_id`, `payment_id`, `payment_status`, `delivery_status` |
| `notification_failure` | `notification_logs.status IN ('failed', 'error')` | warning | `notification_logs` | `notification_id`, `ticket_id`, `channel`, `error_category`, `error_message` |
| `dashboard_api_down` | `/health` 실패 또는 DB 연결 실패 | critical | Dashboard API, DB connection | `endpoint`, `error`, `checked_at` |

### 집계 기반 알림

집계 기반 알림은 짧은 노이즈를 줄이기 위해 기본적으로 최근 30분 또는 최근 1시간 rolling window 기준으로 계산한다.

| Alert Type | Trigger | Severity | Source | 비고 |
| --- | --- | --- | --- | --- |
| `high_risk_spike` | 최근 1시간 HIGH/critical 티켓 수가 `5건 이상` 또는 직전 동시간 대비 `2배 이상` | critical | `ticket_analysis` | 장애성 문의 급증 감지 |
| `negative_sentiment_spike` | 최근 1시간 부정 감성 비율이 `50% 이상`이고 티켓 수가 `10건 이상` | warning | `ticket_analysis`, `insight`, `voc_feedback` | 커뮤니티 여론 악화 감지 |
| `pending_backlog_spike` | `status = 'pending'` 티켓이 `50건 이상` 또는 1시간 전 대비 `30% 이상 증가` | warning | `qa_ticket` | 운영자 처리 병목 감지 |
| `human_review_queue_spike` | `human_review` 대상이 `20건 이상` 또는 1시간 전 대비 `30% 이상 증가` | warning | `qa_ticket`, `ticket_analysis`, `safety_results` | 자동 처리 실패 증가 |
| `low_response_rate` | 최근 24시간 응답률이 `70% 미만`이고 전체 문의가 `20건 이상` | warning | `qa_ticket`, `final_response` | 운영 품질 저하 |
| `low_evidence_attachment_rate` | 최근 24시간 근거 첨부율이 `80% 미만`이고 초안 수가 `20건 이상` | warning | `answer_draft`, `evidence_docs` | RAG 또는 근거 저장 문제 |
| `safety_average_breach` | 평균 환각/유해성/정책 위반이 `0.7 이상` 또는 평균 사실성이 `0.3 이하` | warning | `safety_results` | 모델/프롬프트 품질 저하 |
| `long_pending_ticket` | 닫히지 않은 티켓이 `24시간 이상` 대기 | warning | `qa_ticket` | SLA 위반 후보 |

### 복구 알림

복구 알림은 같은 `alert_type`이 이전에 발송된 뒤 정상 조건으로 돌아왔을 때 1회 발송한다.

| Alert Type | Recovery Rule | 메시지 |
| --- | --- | --- |
| `dashboard_api_recovered` | `/health`가 3회 연속 성공 | 대시보드 API 정상화 |
| `pending_backlog_recovered` | pending backlog가 threshold 미만으로 2회 연속 유지 | 대기 문의 정상 범위 복귀 |
| `safety_average_recovered` | 모든 Safety 평균 지표가 threshold 정상 범위로 2회 연속 유지 | Safety 평균 정상화 |
| `notification_channel_recovered` | 동일 channel의 최근 알림 3건이 성공 | 알림 채널 정상화 |

## Slack 알림 중복 방지

| 항목 | 기준 |
| --- | --- |
| Dedup key | `alert_type + ticket_id` 또는 `alert_type + channel + window_start` |
| 동일 티켓 즉시 알림 | 같은 `alert_type`, `ticket_id`는 30분 내 1회만 발송 |
| 집계 알림 | 같은 `alert_type`, 같은 rolling window는 1회만 발송 |
| 심각도 상승 | warning에서 critical로 상승한 경우 중복 제한과 무관하게 재발송 |
| 알림 저장 | 발송 결과는 `notification_logs`에 `channel`, `status`, `message`, `error_message`, `error_category`, `sent_at`으로 추적 |

## Slack 메시지 포맷

Slack 메시지는 운영자가 바로 판단할 수 있게 원인, 규모, 바로가기 정보를 포함한다. 개인정보와 결제 식별자는 마스킹한다.

```text
[대시보드 알림] {severity} - {alert_type}
- 발생 시각: {checked_at}
- 기준: {trigger_rule}
- 대상: ticket_id={ticket_id or count}, account_id={masked_account_id}
- 요약: {summary}
- 확인: /dashboard/tickets/{ticket_id} 또는 /dashboard/{section}
```

## API 응답 권장 필드

`/summary/*` 응답에는 화면 표시와 알림 판단에 필요한 값을 함께 포함한다.

| Endpoint | 권장 필드 |
| --- | --- |
| `/summary/overview` | `ticket_counts`, `response_metrics`, `coverage_metrics`, `source_distribution`, `status_distribution`, `routing_distribution`, `old_pending_count`, `recent_tickets` |
| `/summary/risk` | `analysis_risk_distribution`, `sentiment_distribution`, `insight_risk_distribution`, `pattern_risk_distribution`, `safety_score_summary`, `safety_alerts`, `high_risk_tickets`, `safety_breach_candidates` |
| `/summary/quality` | `draft_summary`, `evidence_summary`, `safety_summary`, `final_response_summary`, `notification_summary`, `quality_candidates`, `notification_failures` |
| `/tickets` | `ticket_id`, `title`, `status`, `source_type`, `nickname`, `category`, `risk_level`, `sentiment`, `routing_target`, `latest_draft_id`, `latest_response_id`, `inquiry_created_at` |
| `/tickets/{ticket_id}` | `ticket`, `account`, `analyses`, `drafts`, `evidence_docs`, `safety_results`, `final_responses`, `notifications`, `voc_feedback`, `operation_logs` |
