# Conceptual Data Model

## 목적

실제 SQL 작성 전에 어떤 데이터가 필요한지 정리하는 문서입니다.

## 핵심 엔터티 후보

- `qa_ticket`: 고객 문의 원본
- `ticket_analysis`: 분류/분석 결과
- `answer_draft`: 생성된 응답 초안
- `evidence_docs`: 근거 문서 연결
- `safety_results`: 안전성 점검 결과
- `human_feedback`: 운영자 승인/수정/반려 기록
- `operation_reports`: 운영 리포트
- `operation_risk_alerts`: 위험 알림
- `faq_update_candidates`: FAQ 개선 후보
- `router_improvement_suggestions`: 라우팅 개선 후보

## 향후 정리할 것

- 각 엔터티의 PK/FK
- 생성 주체와 갱신 주체
- 운영 로그성 테이블과 서비스성 테이블 구분
