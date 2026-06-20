# GameOps Support Platform

게임 고객지원 운영을 위한 모노레포입니다. 현재 저장소는 세 개의 애플리케이션과 하나의 공용 Python 패키지로 구성됩니다.

- `apps/chatbot`: 사용자용 문의 접수 및 답변 생성 챗봇
- `apps/cs_auto`: 운영자용 문의 검토, 초안 수정, 승인 화면과 백엔드
- `apps/weekly_report`: 주간 운영 리포트 생성 및 Slack 발송
- `common`: DB 연결, 문서 처리, 검색, 관측성 등 공용 코드

## Repository Layout

```text
.
├─ apps
│  ├─ chatbot
│  │  ├─ backend
│  │  └─ frontend
│  ├─ cs_auto
│  │  ├─ backend
│  │  ├─ frontend
│  │  └─ deploy
│  ├─ weekly_report
│  │  ├─ airflow
│  │  ├─ api
│  │  └─ ...
│  └─ tests
├─ common
├─ data
│  ├─ keywords
│  └─ sql
├─ deploy
└─ docs
```

## Services

### 1. Chatbot

- FastAPI 엔드포인트: [apps/chatbot/backend/api/main.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/api/main.py)
- 정적 프런트엔드: [apps/chatbot/frontend/static/index.html](/C:/SKN25-FINAL-6Team/apps/chatbot/frontend/static/index.html)
- 주요 기능
  - 계정 로그인
  - 결제 / 버그 / FAQ / VOC 카테고리 라우팅
  - LangGraph 기반 답변 생성
  - 멀티턴 세션 컨텍스트 유지
  - 안전성 검사 및 최종 응답 저장

주요 API:

- `GET /health`
- `GET /server-regions`
- `POST /login`
- `GET /tickets`
- `POST /chat`

### 2. CS Auto

- FastAPI 엔드포인트: [apps/cs_auto/backend/api/main.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/api/main.py)
- 정적 프런트엔드: [apps/cs_auto/frontend/cs_automation.html](/C:/SKN25-FINAL-6Team/apps/cs_auto/frontend/cs_automation.html)
- 주요 기능
  - 운영자 로그인 / 로그아웃
  - 검토 대상 티켓 목록 조회
  - 티켓 상세, 근거 문서, 이력 조회
  - 답변 초안 수정 / 재생성 / 승인
  - 승인 후 고객 답변 메일 발송

주요 API:

- `GET /api/cs-auto/health`
- `GET /api/cs-auto/tickets`
- `GET /api/cs-auto/tickets/{ticket_id}`
- `POST /api/cs-auto/auth/login`
- `PATCH /api/cs-auto/tickets/{ticket_id}/draft`
- `POST /api/cs-auto/tickets/{ticket_id}/draft/regenerate`
- `POST /api/cs-auto/tickets/{ticket_id}/draft/approve`
- `POST /api/cs-auto/tickets/{ticket_id}/send-email`

### 3. Weekly Report

- FastAPI 엔드포인트: [apps/weekly_report/api/main.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/api/main.py)
- 리포트 실행 진입점: [apps/weekly_report/report.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/report.py)
- 주요 기능
  - 기간별 운영 지표 집계
  - 상위 요청 및 이상치 탐지
  - AI 기반 액션 아이템 생성
  - PDF 렌더링
  - Slack 발송

주요 API:

- `GET /health`
- `POST /report/trigger`

## Requirements

- Python 3.12
- PostgreSQL
- `LLM_API_KEY`를 사용할 수 있는 LLM API 접근 권한
- 선택 사항
  - Redis: 챗봇 캐시 사용 시
  - Slack Bot Token: 주간 리포트 발송 시
  - SMTP App Password: CS Auto 메일 발송 시
  - Docker / Docker Compose: 컨테이너 실행 시

## Environment Variables

공용 DB 연결은 [common/db/connection.py](/C:/SKN25-FINAL-6Team/common/db/connection.py) 에서 `.env`를 읽습니다.

기본 `.env` 예시는 [deploy/.env.example](/C:/SKN25-FINAL-6Team/deploy/.env.example) 를 참고하면 됩니다.

최소 필수 값:

```env
DB_HOST=
DB_PORT=5432
DB_USER=
DB_PASSWORD=
DB_NAME=

LLM_API_KEY=
LLM_MODEL=
```

주요 선택 값:

```env
DB_CONNECT_TIMEOUT=15

CHATBOT_CORS_ORIGINS=http://localhost,http://127.0.0.1
CHATBOT_LANGSMITH_TRACING=
CHATBOT_LANGSMITH_API_KEY=
CHATBOT_LANGSMITH_PROJECT=game_chatbot
CHATBOT_DEBUG_ROUTING=false
SLACK_WEBHOOK_URL=

CS_AUTO_ROUTING_MODEL=
CS_AUTO_API_CORS_ORIGINS=*
CS_AUTO_CORS_ORIGINS=
CS_AUTO_REGENERATION_LIMIT=3
CS_AUTO_KEYWORD_DIR=
CS_AUTO_SQL_DIR=
LLM_TIMEOUT_SECONDS=60
SMTP_APP_PASSWORD=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
NAVER_CAFE_COMMENT_ENDPOINT=
OPERATION_LANGSMITH_TRACING=
OPERATION_LANGSMITH_API_KEY=
OPERATION_LANGSMITH_PROJECT=

DASHBOARD_WEEKLY_REPORT_CHANNEL=
DASHBOARD_WEEKLY_REPORT_COMMENT=
DASHBOARD_SLACK_BOT_TOKEN=
```

검색 / 문서 처리 관련 선택 값:

```env
EMBEDDING_MODEL=text-embedding-3-small
RETRIEVAL_TOP_K=3
RETRIEVAL_CANDIDATE_LIMIT=300
RETRIEVAL_BROAD_CANDIDATE_LIMIT=2000
RERANKER_MODEL=
QUERY_ENRICHMENT_MODEL=
```

## Installation

루트 공용 의존성 설치:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

서비스별 의존성은 각 requirements 파일 기준으로 추가 설치할 수 있습니다.

```powershell
python -m pip install -r apps\chatbot\backend\requirements.txt
python -m pip install -r apps\cs_auto\backend\requirements.txt
python -m pip install -r apps\weekly_report\requirements.txt
```

## Local Run

### 1. Chatbot Backend

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team;C:\SKN25-FINAL-6Team\apps\chatbot\backend"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

### 2. Chatbot Frontend

정적 HTML이므로 간단한 파일 서버로 실행하면 됩니다.

```powershell
cd apps\chatbot\frontend\static
python -m http.server 5173
```

브라우저에서 `http://127.0.0.1:5173` 접속할 수 있습니다.
현재 프런트 코드는 `/chatbot/api` 상대 경로로 백엔드를 호출합니다. 따라서 로컬에서 `python -m http.server`만 사용할 경우에는 별도 리버스 프록시를 두거나, 테스트용으로 프런트 코드를 임시 수정해야 합니다.

### 3. CS Auto Backend

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team;C:\SKN25-FINAL-6Team\apps\cs_auto\backend"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

Health check:

```text
http://127.0.0.1:8001/api/cs-auto/health
```

### 4. CS Auto Frontend

`api.js`는 기본적으로 `/cs-auto/api`를 바라보므로, 로컬 테스트 시 간단한 프록시가 없으면 HTML에서 `window.CS_AUTO_API_BASE_URL`을 직접 지정하는 방식이 편합니다.

```powershell
cd apps\cs_auto\frontend
python -m http.server 5174
```

기본 접속 URL:

```text
http://127.0.0.1:5174/cs_automation.html
```

### 5. Weekly Report API

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team;C:\SKN25-FINAL-6Team\apps\weekly_report"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8002
```

Health check:

```text
http://127.0.0.1:8002/health
```

수동 리포트 트리거:

```powershell
Invoke-WebRequest -Method POST http://127.0.0.1:8002/report/trigger
```

## Airflow Jobs

현재 Airflow DAG는 다음 세 개가 포함되어 있습니다.

- `cs_auto_analysis_agent_daily`
  - 파일: [apps/cs_auto/backend/airflow/analysis_agent_dag.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/airflow/analysis_agent_dag.py)
  - 스케줄: 매일 `01:00` KST
- `cs_auto_answer_agent_daily`
  - 파일: [apps/cs_auto/backend/airflow/answer_agent_dag.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/airflow/answer_agent_dag.py)
  - 스케줄: 매일 `04:00` KST
- `dashboard_weekly_report`
  - 파일: [apps/weekly_report/airflow/weekly_report_dag.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/airflow/weekly_report_dag.py)
  - 스케줄: 매주 월요일 `09:00` KST

## Documents Processing

문서 청킹 및 임베딩 재생성 CLI:

- 엔트리포인트: [common/documents_processing/cli.py](/C:/SKN25-FINAL-6Team/common/documents_processing/cli.py)

예시:

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team"
python -m common.documents_processing.cli --source-type faq --limit 10
```

드라이런:

```powershell
python -m common.documents_processing.cli --dry-run --log-level DEBUG
```

## Testing

전체 테스트:

```powershell
pytest
```

영역별 테스트:

```powershell
pytest apps\tests\chatbot_tests
pytest apps\tests\cs-auto_tests
pytest apps\tests\weekly_report_tests
pytest common\tests
```

주의:

- 일부 테스트는 실제 DB 또는 LLM 환경 변수를 기대합니다.
- 통합 성격 테스트는 `.env` 설정 여부에 따라 실패할 수 있습니다.

## Docker Deployment

배포용 compose 파일은 [deploy](/C:/SKN25-FINAL-6Team/deploy) 아래에 분리되어 있습니다.

- [deploy/docker-compose.chatbot.yml](/C:/SKN25-FINAL-6Team/deploy/docker-compose.chatbot.yml)
- [deploy/docker-compose.cs-auto.yml](/C:/SKN25-FINAL-6Team/deploy/docker-compose.cs-auto.yml)
- [deploy/docker-compose.airflow.yml](/C:/SKN25-FINAL-6Team/deploy/docker-compose.airflow.yml)

기본 흐름:

```powershell
cd deploy
Copy-Item .env.example .env
docker compose --env-file .env -f docker-compose.chatbot.yml up -d --build
docker compose --env-file .env -f docker-compose.cs-auto.yml up -d --build
docker compose --env-file .env -f docker-compose.airflow.yml up -d --build
```

자세한 배포 메모는 [deploy/README.md](/C:/SKN25-FINAL-6Team/deploy/README.md) 를 참고합니다.

## Reference Docs

- [docs/weekly_report/architecture.md](/C:/SKN25-FINAL-6Team/docs/weekly_report/architecture.md)
- [docs/weekly_report/prd.md](/C:/SKN25-FINAL-6Team/docs/weekly_report/prd.md)
- [docs/chatbot/refactor-handoff.md](/C:/SKN25-FINAL-6Team/docs/chatbot/refactor-handoff.md)
- [docs/DB/db_info.md](/C:/SKN25-FINAL-6Team/docs/DB/db_info.md)
