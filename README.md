# GameOps Support Platform

게임 문의 처리, 운영 검수, 운영 대시보드를 하나의 저장소에서 관리하는 Python 모노레포입니다. 저장소는 세 개의 서비스와 공통 모듈로 구성됩니다.

- `chatbot`: 사용자 문의를 분류하고 답변 초안을 생성하는 상담 챗봇
- `operation`: 초안 검수, 승인, 반려를 수행하는 운영자 검수 도구
- `dashboard`: 운영 현황, 리스크, 품질, 주간 보고서를 제공하는 분석 대시보드
- `common`: DB 연결, 문서 임베딩 파이프라인, 공통 설정과 관측 기능

## 주요 기능

### 1. 챗봇 서비스

`src/chatbot`은 LangGraph 기반 상담 워크플로우를 제공합니다.

- 문의를 `payment`, `bug`, `faq`, `voc` 계열로 분류
- 유형별 에이전트에서 답변 초안 생성
- FAQ 계열은 문서 검색과 RAG 기반 응답 생성 수행
- 초안, 근거 문서, 안전성 검사 결과를 DB에 저장
- 안전성 레이어에서 환각성, 독성, 정책 위반 가능성을 검사
- 최종 응답 또는 운영 검토 필요 상태를 반환
- FastAPI `POST /chat` API와 Streamlit UI 제공

워크플로우 구성은 `orchestrator -> domain agent -> draft_persistence -> safety_layer -> final_response` 구조입니다. VOC 문의는 초안 저장 단계를 거치지 않고 바로 최종 응답으로 연결됩니다.

### 2. 운영 검수 서비스

`src/operation`은 챗봇이 만든 답변 초안을 운영자가 검토하는 서비스입니다.

- 오늘 확인할 문의 또는 상태별 문의 목록 조회
- 특정 티켓의 분석 결과, 초안, 근거 문서, 안전성 검사, 검수 이력 조회
- 티켓 단위 워크플로우 재실행으로 초안 재생성
- 초안 수정 `PATCH /drafts/{draft_id}`
- 초안 승인 후 `final_response` 저장 및 티켓 종료
- 초안 반려 후 티켓을 `pending` 상태로 되돌리고 재실행 URL 제공
- Streamlit UI에서 문의 목록, 상세, 검수 액션을 함께 처리

### 3. 운영 대시보드

`src/dashboard`는 DB에 저장된 문의 처리 결과를 집계해 운영 현황을 시각화합니다.

- 기간별 전체 문의 처리 현황 요약
- 리스크 수준, 감성, 라우팅 타깃 분포 집계
- 답변 초안/최종 응답/안전성 검사 커버리지 확인
- 티켓 목록과 티켓 상세 이력 조회
- 주간 보고서 미리보기 생성
- 주간 보고서 PDF 생성
- Slack 채널로 주간 보고서 전송
- APScheduler 기반 자동 발송 스케줄러 제공

기본 스케줄러는 `Asia/Seoul` 기준 매주 월요일 09:00에 Slack 전송을 시도합니다.

### 4. 공통 데이터 처리

`src/common`에는 여러 서비스가 공유하는 기반 기능이 들어 있습니다.

- PostgreSQL 연결 관리
- LangSmith 관측 설정
- 문서 정규화, 청킹, 임베딩, 저장 파이프라인
- CLI 기반 문서 임베딩 재구축

문서 파이프라인 CLI:

```bash
python -m src.common.documents_processing.cli --source-type faq --limit 100
```

선택 옵션:

- `--document-id`
- `--source-type`
- `--category`
- `--limit`
- `--dry-run`

## 저장소 구조

```text
src/
  chatbot/
    api/
    frontend/
    chains/
    generation/
    retrieval/
    repository/
    service/
  operation/
    api/
    frontend/
    workflow/
  dashboard/
    api/
    frontend/
    workflow/
  common/
    db/
    documents_processing/
    observability/
    utils/
tests/
docs/
deploy/
data/
```

## 기술 스택

- API: FastAPI, Uvicorn
- UI: Streamlit
- 워크플로우: LangGraph
- LLM 연동: `langchain-openai`
- 데이터 저장: PostgreSQL, pgvector
- 대시보드 시각화: Pandas, Plotly
- 스케줄링: APScheduler
- 알림: Slack SDK
- 보고서 생성: `xhtml2pdf`
- 테스트: Pytest

## 환경 변수

기본 환경 변수는 `.env.example`에 정의되어 있습니다. 로컬 실행 전 `.env`를 준비해야 합니다.

핵심 항목:

```env
DB_HOST=
DB_PORT=5432
DB_USER=
DB_NAME=
DB_PASSWORD=

LLM_API_KEY=
LLM_MODEL=

CHATBOT_API_BASE_URL=http://chatbot-backend:8000
OPERATION_API_BASE_URL=http://operation-backend:8000
DASHBOARD_API_BASE_URL=http://dashboard-backend:8000

DASHBOARD_SLACK_BOT_TOKEN=
DASHBOARD_WEEKLY_REPORT_CHANNEL=#ops-dashboard
DASHBOARD_WEEKLY_REPORT_AUTOSTART=1
```

선택 항목:

- 서비스별 LangSmith 추적 설정
- `CHATBOT_DEBUG_ROUTING`
- `DASHBOARD_WEEKLY_REPORT_COMMENT`
- 로컬 포트 오버라이드를 위한 `*_API_HOST`, `*_API_PORT`, `*_FRONTEND_HOST`, `*_FRONTEND_PORT`

## 실행 방법

### 1. Docker Compose 실행

현재 `docker-compose.yml` 기준 MVP 배포 대상은 `operation`, `dashboard`입니다. `chatbot` 컨테이너는 주석 처리되어 있습니다.

```bash
docker compose up -d --build
docker compose ps
```

접속 경로:

- `http://localhost/operation/`
- `http://localhost/dashboard/`
- `http://localhost/operation/api/health`
- `http://localhost/dashboard/api/health`

### 2. 로컬 실행

의존성 설치:

```bash
pip install -r requirements.txt
```

운영 검수 UI + API 동시 실행:

```bash
python -m src.operation.run
```

대시보드 UI + API 동시 실행:

```bash
python -m src.dashboard.run
```

챗봇 API 단독 실행:

```bash
python -m uvicorn src.chatbot.api.main:app --host 127.0.0.1 --port 8000
```

챗봇 UI 실행:

```bash
python -m streamlit run src/chatbot/frontend/app.py
```

기본 로컬 포트:

- Operation API: `8001`
- Operation UI: `8501`
- Dashboard API: `8010`
- Dashboard UI: `8510`
- Chatbot API: `8000`

## 주요 API

### 챗봇 API

- `GET /health`
- `POST /chat`

`POST /chat` 요청 필드:

- `ticket_id`
- `user_message`
- `account_id`
- `user_id`
- `session_id`
- `source_type`
- `previous_messages`

### 운영 검수 API

- `GET /health`
- `POST /tickets/{ticket_id}/run-workflow`
- `GET /tickets`
- `GET /tickets/today`
- `GET /tickets/{ticket_id}`
- `PATCH /drafts/{draft_id}`
- `POST /drafts/{draft_id}/approve`
- `POST /drafts/{draft_id}/reject`

### 대시보드 API

- `GET /health`
- `GET /summary/overview`
- `GET /summary/risk`
- `GET /summary/quality`
- `GET /summary/all`
- `GET /reports/weekly`
- `GET /reports/weekly/pdf`
- `POST /reports/weekly/slack`
- `POST /reports/weekly/slack/now`
- `GET /tickets`
- `GET /tickets/{ticket_id}`

## 테스트

테스트는 서비스별로 분리되어 있습니다.

- `tests/chatbot`
- `tests/operation`
- `tests/dashboard`
- `tests/common`

전체 테스트 실행:

```bash
pytest
```

서비스별 실행 예시:

```bash
pytest tests/chatbot
pytest tests/operation
pytest tests/dashboard
```

## 참고 문서

- 챗봇 설계: `docs/chatbot`
- 운영 검수 설계: `docs/operation`
- 대시보드 설계: `docs/dashboard`
- DB 문서: `docs/DB`
- 배포 가이드: `deploy/README.md`
