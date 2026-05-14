# Game CS Automation System

게임 고객 문의를 수집, 분류, 초안 응답 생성, 운영 검토, 운영 인사이트 분석까지 연결하는 AI 기반 CS 자동화 시스템의 초기 설계 문서입니다.

현재 단계에서는 구현 코드보다 아래 3가지를 먼저 고정합니다.

1. 프로젝트의 목적과 범위
2. 폴더 구조
3. 외부 PostgreSQL + `psql` 기준 환경 변수 규칙

## 용도

이 프로젝트는 게임 서비스 운영 과정에서 반복적으로 들어오는 고객 문의를 더 빠르게 처리하기 위한 백엔드/운영 자동화 시스템을 목표로 합니다.

주요 사용 시나리오는 다음과 같습니다.

- FAQ성 문의에 대한 자동 분류와 응답 초안 생성
- 결제, 환불, 아이템 지급, 버그 제보 같은 운영 문의의 라우팅
- 위험 문의에 대한 Human-in-the-loop 검토
- 운영 로그와 문의 데이터를 기반으로 한 주간 리포트, 이슈 탐지, FAQ 개선 후보 도출

즉, 단순 챗봇 하나가 아니라 다음 세 영역을 함께 다루는 구조를 전제로 합니다.

- 실시간 챗봇 응답
- 운영 배치 처리
- 운영 분석 Deep Agent

## 개발 기준

초기 개발은 Docker가 아니라 외부 PostgreSQL 서버와 `psql` 기준으로 진행합니다.

원칙은 다음과 같습니다.

- 모든 DB 연결은 `DATABASE_URL` 하나로 통일합니다.
- 코드나 스크립트에 `localhost`, 컨테이너 서비스명, 특정 호스트를 하드코딩하지 않습니다.
- 스키마 관리는 `sql/` 아래 SQL 파일 기준으로 진행합니다.
- 초기에 필요한 검증은 `psql`로 직접 schema/seed를 반영하는 방식으로 맞춥니다.

예시 실행 흐름:

```bash
psql "$DATABASE_URL" -f sql/schema.sql
psql "$DATABASE_URL" -f sql/indexes.sql
psql "$DATABASE_URL" -f sql/seed.sql
```

## 예정 프레임워크 및 기술 스택

README 초안 기준으로 현재 계획하는 기술 스택은 아래와 같습니다.

- Backend language: Python
- API framework: FastAPI
- Agent orchestration: LangGraph
- Tool-calling agents: LangChain `create_agent`
- Deep analysis agent: 별도 Deep Agent 모듈
- Database: PostgreSQL
- Vector search: `pgvector` 또는 PostgreSQL 기반 벡터 저장소
- Deployment target: 추후 Supabase + 별도 worker/runtime

정리하면, 현재는 `Python + FastAPI + LangGraph + PostgreSQL` 조합으로 백엔드 골격을 먼저 잡고, 이후 필요 시 배포 구조를 `Supabase + 별도 worker/runtime` 방향으로 확장하는 구조입니다.

## 폴더 구조

아직 구현 파일은 만들지 않고, README에서 제안한 책임 분리 기준으로 디렉터리만 먼저 구성합니다.

```text
.
|-- apps/
|   |-- api/
|   |   `-- routes/
|   |-- chatbot/
|   |   |-- nodes/
|   |   `-- prompts/
|   |-- operation_batch/
|   |   |-- jobs/
|   |   `-- nodes/
|   |-- operation_insight/
|   |   |-- prompts/
|   |   |-- reports/
|   |   `-- tools/
|-- packages/
|   |-- common/
|   |-- db/
|   |   |-- models/
|   |   `-- repositories/
|   |-- rag/
|   |-- llm/
|   |-- tools/
|   |-- safety/
|   |-- observability/
|   `-- deep_agents/
|       |-- subagents/
|       |-- report/
|       `-- memory/
|-- sql/
|   `-- migrations/
|-- docker/
|-- docs/
|   |-- architecture/
|   |-- requirements/
|   |-- erd/
|   |-- api/
|   `-- deployment/
|-- data/
|   |-- raw/
|   |-- processed/
|   `-- vector_store/
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- graph/
|   `-- deep_agent/
`-- scripts/
```

## 디렉터리 역할

- `apps/`: 실행 단위별 애플리케이션
- `apps/api/`: 외부 API 진입점
- `apps/chatbot/`: 실시간 문의 처리 그래프와 에이전트 노드
- `apps/operation_batch/`: 배치 수집/분석/승인 대기 흐름
- `apps/operation_insight/`: 운영 리포트와 Deep Agent 분석
- `packages/`: 공통 모듈
- `packages/db/`: DB 연결, 모델, 저장소 계층
- `packages/rag/`: 문서 로딩, 분할, 임베딩, 검색
- `packages/llm/`: LLM 클라이언트와 에이전트 팩토리
- `packages/tools/`: 결제/환불/로그 조회 등 툴 모듈
- `packages/safety/`: 환각성, 독성, 정책 위반 등 안전성 점검
- `packages/observability/`: 로깅, 추적, 평가 지표
- `packages/deep_agents/`: 운영 분석용 공통 Deep Agent 로직
- `sql/`: 스키마, 인덱스, 시드, 마이그레이션 SQL
- `docs/`: 아키텍처, 요구사항, ERD, 배포 문서
- `data/`: 원천 데이터, 전처리 데이터, 벡터 저장소
- `tests/`: 단위/통합/그래프/Deep Agent 테스트
- `scripts/`: 로컬 실행, 배치 실행, 인덱스 생성 등 보조 스크립트

## 환경 변수 규칙

초기 기준은 외부 PostgreSQL 접속입니다.

`DATABASE_URL` 예시는 아래 형식을 사용합니다.

```env
postgresql://USERNAME:PASSWORD@HOST:5432/DATABASE_NAME
```

추가 규칙:

- DB 호스트는 외부 PostgreSQL 주소를 사용합니다.
- 로컬 전용 값이 필요해도 코드에서는 직접 참조하지 않고 `.env`에서만 관리합니다.
- 추후 Supabase로 전환하더라도 애플리케이션 레벨에서는 가능한 한 `DATABASE_URL` 중심으로 유지합니다.

## 현재 상태

현재 커밋 기준으로 반영된 것은 다음뿐입니다.

- README 정리
- 기본 폴더 구조 생성
- `.env.sample` 작성

아직 구현하지 않은 것:

- Python 실행 코드
- API 라우트
- SQL 스키마
- 프론트엔드 화면
- 배치/에이전트 로직

다음 단계부터는 이 구조를 기준으로 실제 `schema.sql`, 실행 엔트리, 공통 설정을 채우면 됩니다.
