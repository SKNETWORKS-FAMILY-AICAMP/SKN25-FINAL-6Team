# Dashboard

STEP3 운영 인사이트와 observability 전용 에이전트다.

## 범위

- 운영 통계 집계
- 동일 문의 반복 여부 분석
- 감성 변화 추이 분석
- 위험 키워드 증가율 추적
- 승인율 / 수정율 / 재문의율 추적
- Slack / Discord 알림 기준 생성

## 제외 범위

- STEP1 문의 유형 분석
- STEP2 답변 초안 생성
- Approval Gate
- Human-in-the-loop 답변 검수

## 구현 메모

- 에이전트 엔트리포인트는 `agent.py`
- `create_agent`를 사용한다
- 입력 데이터는 `ticket_analysis`, `safety_results`, `final answer outcomes`를 중심으로 한다
