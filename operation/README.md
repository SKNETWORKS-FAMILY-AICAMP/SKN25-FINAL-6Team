# Operation

운영 배치의 STEP1과 STEP2를 한 번에 수행하는 에이전트다.

## 범위

- STEP1: 문의 유형 분석 및 Query Routing
- STEP2: RAG 검색 및 답변 초안 생성
- Approval Gate: 답변 안전성 검증
- Human-in-the-loop: 운영자 최종 검수

## 제외 범위

- STEP3: 운영 인사이트 생성
- Observability Layer: 지표 수집, 알림, 추이 분석

STEP3와 observability는 `dashboard` 에이전트가 담당한다.

## 주요 역할

- `QA_ticket` 기반 문의 원문 저장 및 분석
- `community_users`, `game_accounts`, `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` 조회
- FAQ, 공지, 정책 문서 RAG 검색
- 답변 초안 생성
- 안전성 검사와 운영자 검수용 데이터 준비

## 구현 메모

- 에이전트 엔트리포인트는 `agent.py`
- `create_agent`를 사용한다
- 실제 DB 연동과 리트리버 구현은 서비스 계층에서 연결한다
