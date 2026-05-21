# Dashboard Metrics

이 문서는 `docs/DB/descriptions.md`의 실제 테이블과 컬럼을 기준으로, 대시보드에서 보여줄 지표를 정의한다. 수치는 모두 PostgreSQL에서 집계한다.

## 운영 현황

| Metric | Definition | Source |
| --- | --- | --- |
| Ticket volume | 조회 기간 내 `qa_ticket` 건수 | `qa_ticket` |
| Pending backlog | `status = 'pending'` 건수 | `qa_ticket` |
| Closed tickets | `status = 'closed'` 건수 | `qa_ticket` |
| Today received | `inquiry_created_at`가 당일인 건수 | `qa_ticket` |
| Response rate | `final_response`가 존재하는 티켓 비율 | `qa_ticket`, `final_response` |
| Avg response latency | `final_response.created_at - qa_ticket.inquiry_created_at` 평균 | `qa_ticket`, `final_response` |
| Source mix | `source_type`별 티켓 분포 | `qa_ticket` |
| Routing mix | 최신 `ticket_analysis.routing_target` 분포 | `ticket_analysis` |

## 리스크 분석

| Metric | Definition | Source |
| --- | --- | --- |
| Analysis risk mix | 최신 `ticket_analysis.risk_level` 분포 | `ticket_analysis` |
| Sentiment mix | 최신 `ticket_analysis.sentiment` 분포 | `ticket_analysis` |
| Insight risk mix | `insight.risk_level` 분포 | `insight` |
| Pattern risk mix | `insight.pattern_risk_level` 분포 | `insight` |
| Avg hallucination score | `safety_results.hallucination_score` 평균 | `safety_results` |
| Avg toxicity score | `safety_results.toxicity_score` 평균 | `safety_results` |
| Avg policy violation score | `safety_results.policy_violation_score` 평균 | `safety_results` |
| Avg factuality score | `safety_results.factuality_score` 평균 | `safety_results` |
| High-risk ticket list | 최신 분석 기준 상위 위험 티켓 | `ticket_analysis`, `qa_ticket`, `insight` |

## 응답 품질

| Metric | Definition | Source |
| --- | --- | --- |
| Draft coverage | `answer_draft`가 존재하는 티켓 비율 | `qa_ticket`, `answer_draft` |
| Evidence attachment rate | `evidence_docs`가 1건 이상인 초안 비율 | `answer_draft`, `evidence_docs` |
| Avg evidence relevance | `evidence_docs.relevance_score` 평균 | `evidence_docs` |
| Final response coverage | `final_response`가 존재하는 티켓 비율 | `qa_ticket`, `final_response` |
| Safety check count | `safety_results` 건수 | `safety_results` |
| Notification status mix | `notification_logs.status` 분포 | `notification_logs` |
| Delivery latency | `notification_logs.sent_at`와 `final_response.created_at` 차이 | `final_response`, `notification_logs` |

## Scoring rule

- 평균 점수는 raw numeric 값을 그대로 보여준다.
- 고위험 판정은 지표 정의를 고정하지 않고, API에서 임계값 파라미터를 받을 수 있게 설계한다.
- 기본 화면은 분포와 평균을 우선 보여주고, 상세 화면에서 특정 티켓의 원문과 근거를 같이 확인한다.

## Recommended thresholds

기본 시각화용 기준값이다. 모델/룰이 바뀌면 API 파라미터로 조정한다.

| Metric | Threshold |
| --- | --- |
| High hallucination | `>= 0.7` |
| High toxicity | `>= 0.7` |
| High policy violation | `>= 0.7` |
| Low factuality | `<= 0.3` |

