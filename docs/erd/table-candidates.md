# Table Candidates

## 초기 후보 테이블

- `qa_ticket`
- `ticket_analysis`
- `answer_draft`
- `evidence_docs`
- `safety_results`
- `human_feedback`
- `payments`
- `refunds`
- `item_delivery_logs`
- `gacha_logs`
- `voice_cluster`
- `operation_reports`
- `operation_risk_alerts`
- `faq_update_candidates`
- `router_improvement_suggestions`

## 작성 원칙

- PostgreSQL 표준 문법을 우선 사용
- `created_at`, `updated_at` 같은 공통 감사 컬럼을 고려
- 인덱스는 `schema.sql`과 분리해서 관리 가능하도록 설계
