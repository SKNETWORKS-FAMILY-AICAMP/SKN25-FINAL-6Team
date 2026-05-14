# System Overview

## 목적

이 시스템은 게임 고객 문의를 자동화하되, 위험한 응답은 사람 검토로 넘기고, 누적 데이터는 운영 분석에 다시 활용하는 구조를 목표로 합니다.

## 핵심 구성

- Access Layer: 사용자 문의, 외부 API 진입점
- Orchestration Layer: 문의 저장, 라우팅, 그래프 흐름 제어
- Intelligence Layer: FAQ, 결제, 버그, 보이스 성격의 처리 노드
- Safety Layer: 환각성, 독성, 정책 위반, 검토 필요 여부 판단
- Human-in-the-loop Layer: 운영 승인, 수정 승인, 반려
- Observability Layer: 요청/응답/품질 지표 기록
- Operation Insight Layer: 주간 리포트, 이상 징후 탐지, FAQ 개선 후보
- Data Layer: PostgreSQL, 벡터 검색, 운영 로그 조회

## 예정 프레임워크

- Python
- FastAPI
- LangGraph
- LangChain `create_agent`
- PostgreSQL
- Next.js

## 현재 단계에서 확정하는 것

- 디렉터리 구조
- 외부 PostgreSQL + `psql` 기준 개발 방식
- 서비스 책임 분리 기준

## 아직 확정하지 않은 것

- 실제 테이블 컬럼 상세
- 개별 API request/response 스키마
- 프론트엔드 화면 상세
- 모델별 프롬프트와 에이전트 구현
