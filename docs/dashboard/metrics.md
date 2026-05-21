# Dashboard Metrics

이 문서는 `docs/DB/descriptions.md`의 실제 테이블과 컬럼 기준으로 대시보드 계산식을 정의한다. 모든 집계는 PostgreSQL에서 조회하고, 비율 계산은 `src/dashboard/workflow/nodes.py`의 compute 노드에서 수행한다.

## 공통 필터

- 조회 기간: `qa_ticket.inquiry_created_at >= window_start`
- `window_start = datetime.now() - timedelta(days=days)`
- 기본 `days = 30`, API 허용 범위는 1일부터 365일까지다.

## 운영 현황

| Metric | Formula | Source |
| --- | --- | --- |
| 전체 문의 | `COUNT(*)` | `qa_ticket` |
| 대기 문의 | `COUNT(*) FILTER (WHERE status = 'pending')` | `qa_ticket` |
| 종료 문의 | `COUNT(*) FILTER (WHERE status = 'closed')` | `qa_ticket` |
| 오늘 접수 | `COUNT(*) FILTER (WHERE inquiry_created_at >= CURRENT_DATE AND inquiry_created_at < CURRENT_DATE + INTERVAL '1 day')` | `qa_ticket` |
| 응답률 | `responded_tickets / total_tickets` | `qa_ticket`, `final_response` |
| 초안 커버리지 | `draft_tickets / total_tickets` | `qa_ticket`, `answer_draft` |
| 분석 커버리지 | `analyzed_tickets / total_tickets` | `qa_ticket`, `ticket_analysis` |
| 평균 응답 지연 | `AVG(EXTRACT(EPOCH FROM final_response.created_at - qa_ticket.inquiry_created_at) / 60)` | `qa_ticket`, `final_response` |
| 접수 채널 분포 | `GROUP BY source_type` | `qa_ticket` |
| 상태 분포 | `GROUP BY status` | `qa_ticket` |
| 라우팅 대상 분포 | 최신 `ticket_analysis.routing_target` 기준 `GROUP BY` | `ticket_analysis` |

## 리스크 분석

| Metric | Formula | Source |
| --- | --- | --- |
| 분석 리스크 분포 | 최신 `ticket_analysis.risk_level` 기준 `GROUP BY` | `ticket_analysis` |
| 감성 분포 | 최신 `ticket_analysis.sentiment` 기준 `GROUP BY` | `ticket_analysis` |
| 인사이트 리스크 분포 | `GROUP BY insight.risk_level` | `insight` |
| 패턴 리스크 분포 | `GROUP BY insight.pattern_risk_level` | `insight` |
| 평균 환각 점수 | `AVG(safety_results.hallucination_score)` | `safety_results` |
| 평균 유해성 점수 | `AVG(safety_results.toxicity_score)` | `safety_results` |
| 평균 정책 위반 점수 | `AVG(safety_results.policy_violation_score)` | `safety_results` |
| 평균 사실성 점수 | `AVG(safety_results.factuality_score)` | `safety_results` |
| 고위험 후보 | 최신 분석 또는 인사이트 패턴 리스크가 `high`, `critical`인 티켓 | `qa_ticket`, `ticket_analysis`, `insight` |

## 응답 품질

| Metric | Formula | Source |
| --- | --- | --- |
| 초안 수 | `COUNT(DISTINCT answer_draft.draft_id)` | `answer_draft` |
| 초안 티켓률 | `draft_ticket_count / ticket_count` | `qa_ticket`, `answer_draft` |
| 근거 연결 초안 | `COUNT(draft_id) WHERE EXISTS evidence_docs` | `answer_draft`, `evidence_docs` |
| 근거 첨부율 | `evidence_linked_drafts / draft_count` | `answer_draft`, `evidence_docs` |
| 평균 근거 관련도 | `AVG(evidence_docs.relevance_score)` | `evidence_docs` |
| 평균 근거 순위 | `AVG(evidence_docs.retrieval_rank)` | `evidence_docs` |
| 최종 응답 수 | `COUNT(DISTINCT final_response.response_id)` | `final_response` |
| 최종 응답률 | `final_response_ticket_count / ticket_count` | `qa_ticket`, `final_response` |
| 평균 최종 지연 | `AVG(EXTRACT(EPOCH FROM final_response.created_at - qa_ticket.inquiry_created_at) / 60)` | `qa_ticket`, `final_response` |
| 알림 상태 분포 | `GROUP BY notification_logs.status` | `notification_logs` |
| 품질 점검 후보 | 낮은 `factuality_score`, 높은 `hallucination_score` 우선 정렬 | `answer_draft`, `safety_results` |

## Alert Threshold

기본 threshold는 프론트엔드 표시에 사용하는 참고값이다.

| Alert | Rule |
| --- | --- |
| 높은 환각 | `avg_hallucination_score >= 0.7` |
| 높은 유해성 | `avg_toxicity_score >= 0.7` |
| 높은 정책 위반 | `avg_policy_violation_score >= 0.7` |
| 낮은 사실성 | `avg_factuality_score <= 0.3` |
