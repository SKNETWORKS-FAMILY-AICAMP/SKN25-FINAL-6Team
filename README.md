# GameOps Support Platform

현재 저장소는 `apps` 기준으로 분리된 3개 앱과 공용 Python 패키지로 구성됩니다.

- `apps/chatbot`: 사용자 문의 접수와 답변 초안 생성
- `apps/cs_auto`: 운영자 검수와 초안 승인/반려
- `apps/weekly_report`: 주간 운영 리포트 생성 및 Slack 발송
- `packages/common-python`: DB 연결, 문서 처리, 공용 유틸

## Current Layout

```text
C:\SKN25-FINAL-6Team
|- apps
|  |- chatbot
|  |  |- backend
|  |  |- frontend
|  |  `- deploy
|  |- cs_auto
|  |  |- backend
|  |  |- frontend
|  |  `- deploy
|  `- weekly_report
|     |- airflow
|     |- api
|     `- deploy
|- packages
|  `- common-python
|- docs
|- data
`- docker-compose.yml
```

## Prerequisites

- Python 3.12
- Node.js 22+
- npm
- PostgreSQL / pgvector reachable from this machine
- `.env` configured at the repo root

## Required Environment

루트 `.env`에 최소한 아래 값이 있어야 합니다.

```env
DB_HOST=
DB_PORT=5432
DB_USER=
DB_PASSWORD=
DB_NAME=

LLM_API_KEY=
LLM_MODEL=

DASHBOARD_SLACK_BOT_TOKEN=
DASHBOARD_WEEKLY_REPORT_CHANNEL=#ops-dashboard
```

## Local Run

백엔드는 각 앱의 `backend` 디렉터리에서 실행해야 합니다. 공용 패키지와 앱 패키지를 찾을 수 있도록 `PYTHONPATH`를 같이 설정합니다.

### 1. Chatbot

백엔드:

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team\packages\common-python\src;C:\SKN25-FINAL-6Team\apps\chatbot\backend"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

프런트:

```powershell
cd apps\chatbot\frontend
$env:VITE_CHATBOT_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

### 2. CS Auto

백엔드:

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team\packages\common-python\src;C:\SKN25-FINAL-6Team\apps\cs_auto\backend"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

프런트:

```powershell
cd apps\cs_auto\frontend
$env:VITE_OPERATION_API_BASE_URL="http://127.0.0.1:8001"
npm run dev -- --host 127.0.0.1 --port 5174
```

### 3. Weekly Report

백엔드:

```powershell
$env:PYTHONPATH="C:\SKN25-FINAL-6Team\packages\common-python\src;C:\SKN25-FINAL-6Team\apps\weekly_report"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8002
```

프런트:

```powershell
curl http://127.0.0.1:8002/health
```

## Local URLs

- `chatbot` frontend: `http://127.0.0.1:5173`
- `chatbot` backend: `http://127.0.0.1:8000`
- `cs_auto` frontend: `http://127.0.0.1:5174`
- `cs_auto` backend: `http://127.0.0.1:8001`
- `weekly_report` backend: `http://127.0.0.1:8002`

Health check:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8001/health`
- `http://127.0.0.1:8002/health`

## Docker Compose

루트 `docker-compose.yml`은 현재 `apps` 구조 기준으로 정리되어 있습니다.

```bash
docker compose up -d
docker compose ps
```

Airflow 배치를 같이 띄울 때:

```bash
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-webserver airflow-scheduler
```

Airflow UI:

- `http://localhost:8080`
- 기본 계정: `admin / admin`

cs_auto 배치 DAG:

- `cs_auto_ticket_analysis_daily`: 매일 `02:00` KST에 미분석 티켓 분석
- `cs_auto_naver_cafe_draft_daily`: 매일 `03:00` KST에 `naver_cafe` 티켓 초안 생성
- 수동 검증 테스트는 `apps/tests/cs_auto_tests/test_airflow_jobs.py`를 실행

배치 결과 파일 로그:

- 기본 경로: `logs/operation/airflow/`
- 각 실행마다 JSON 파일 1개 생성

기본 노출 경로:

- `http://localhost/chatbot/`
- `http://localhost/chatbot/api/health`
- `http://localhost/cs-auto/`
- `http://localhost/cs-auto/api/health`
- `http://localhost/weekly-report/api/health`

주의:

- 첫 기동 시 컨테이너 안에서 `pip install`과 `npm ci`가 실행됩니다.
- Docker 컨테이너에서도 루트 `.env`를 사용합니다.
- Docker에서 외부 DB를 쓸 경우 `DB_HOST=localhost`는 사용하면 안 됩니다.

## Tests

전체 테스트:

```bash
pytest
```

앱별 테스트:

```bash
pytest apps/tests/chatbot_tests
pytest apps/tests/cs_auto_tests
pytest apps/tests/weekly_report_tests
```
