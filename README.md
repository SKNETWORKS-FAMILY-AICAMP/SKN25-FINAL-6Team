# GameOps Support Platform

게임 문의 처리, 답변 초안 생성, 운영 검수, 운영 대시보드를 하나의 저장소에서 관리하는 Python 기반 프로젝트입니다. 저장소는 `chatbot`, `operation`, `dashboard`, `common` 모듈을 중심으로 구성되어 있습니다.

- `chatbot`: 사용자 문의를 분류하고 답변 초안을 생성하는 상담 챗봇
- `operation`: 초안 검수, 승인, 반려를 처리하는 운영 검수 도구
- `dashboard`: 운영 현황, 리스크, 주간 보고서를 제공하는 분석 대시보드
- `common`: DB 연결, 문서 처리 파이프라인, 공통 설정과 관측 기능

## 주요 기능

### 1. 챗봇 서비스

`src/chatbot`은 LangGraph 기반 상담 워크플로우를 제공합니다.

- 문의를 `payment`, `bug`, `faq`, `voc` 계열로 분류
- 유형별 에이전트에서 답변 초안 생성
- FAQ 계열은 문서 검색과 RAG 기반 응답 생성 수행
- 초안, 근거 문서, 안전성 검토 결과를 DB에 저장
- 안전성 레이어에서 민감성, 적합성, 정책 위반 가능성 검토
- 최종 응답 또는 운영 검수 필요 상태 반환
- FastAPI `POST /chat` API와 Streamlit UI 제공

워크플로우 구성은 `orchestrator -> domain agent -> draft_persistence -> safety_layer -> final_response` 구조입니다. VOC 문의는 초안 생성 단계를 거치지 않고 바로 최종 응답으로 연결됩니다.

### 2. 운영 검수 서비스

`src/operation`은 챗봇이 만든 답변 초안을 운영자가 검수하는 서비스입니다.

- 오늘 접수된 문의와 상태별 문의 목록 조회
- 특정 티켓의 분석 결과, 초안, 근거 문서, 안전성 검토 이력 조회
- 티켓 단위 워크플로우 재실행으로 초안 재생성
- 초안 수정 `PATCH /drafts/{draft_id}`
- 초안 승인 시 `final_response` 저장 후 티켓 종료
- 초안 반려 시 티켓을 `pending` 상태로 되돌리고 재처리 URL 제공
- Streamlit UI에서 목록, 상세, 검수 액션 제공

### 3. 운영 대시보드

`src/dashboard`는 DB에 저장된 문의 처리 결과를 집계하고 시각화합니다.

- 기간별 전체 문의 처리 현황 요약
- 리스크 점수, 감성, 이슈 분포 집계
- 초안, 최종 응답, 안전성 검토 품질 확인
- 티켓 목록과 상세 이력 조회
- 주간 보고서 미리보기 생성
- 주간 보고서 PDF 생성
- Slack 채널로 주간 보고서 전송
- APScheduler 기반 자동 발송 스케줄러 제공

기본 스케줄러는 `Asia/Seoul` 기준 매주 월요일 `09:00`에 Slack 전송을 시도합니다.

### 4. 공통 데이터 처리

`src/common`에는 여러 서비스가 공유하는 기반 기능이 들어 있습니다.

- PostgreSQL 연결 관리
- LangSmith 관측 설정
- 문서 정규화, 청킹, 임베딩 파이프라인
- CLI 기반 문서 처리 도구 제공

문서 처리 CLI 예시:

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
C:\SKN25-FINAL-6Team
├─ .env.example
├─ docker-compose.yml
├─ README.md
├─ requirements.txt
├─ data     
├─ deploy
│  ├─ README.md
│  ├─ docker
│  │  └─ python-app.Dockerfile
│  └─ nginx
│     └─ default.conf
├─ docs #각 기능별 정리.md
│  ├─ documents_processings.md
│  ├─ chatbot
│  ├─ dashboard
│  ├─ DB
│  ├─ data_generation
│  ├─ deploy
│  └─ operation
├─ src
│  ├─ chatbot
│  │  ├─ CLAUDE.md
│  │  ├─ README.md
│  │  ├─ __init__.py
│  │  ├─ agent.py
│  │  ├─ constants.py
│  │  ├─ schemas.py
│  │  ├─ api
│  │  │  ├─ __init__.py
│  │  │  └─ main.py
│  │  ├─ chains
│  │  │  ├─ __init__.py
│  │  │  ├─ faq_rag.py
│  │  │  ├─ persistence.py
│  │  │  ├─ routing.py
│  │  │  └─ workflow.py
│  │  ├─ evals
│  │  │  ├─ __init__.py
│  │  │  ├─ build_faq_eval_dataset.py
│  │  │  ├─ faq_ragas_eval.py
│  │  │  ├─ generate_faq_responses.py
│  │  │  ├─ run_chatbot_test_report.py
│  │  │  ├─ run_rag_quality_checks.py
│  │  │  └─ run_routing_latency_eval.py
│  │  ├─ frontend
│  │  │  ├─ README.md
│  │  │  ├─ __init__.py
│  │  │  ├─ app.py
│  │  │  ├─ components
│  │  │  │  ├─ __init__.py
│  │  │  │  ├─ chat_input.py
│  │  │  │  ├─ chat_message.py
│  │  │  │  ├─ login_form.py
│  │  │  │  └─ source_box.py
│  │  │  ├─ pages
│  │  │  │  └─ 1_챗봇.py
│  │  │  └─ state
│  │  │     ├─ __init__.py
│  │  │     └─ session_state.py
│  │  ├─ generation
│  │  │  ├─ __init__.py
│  │  │  ├─ bug_agent.py
│  │  │  ├─ drafting_agent.py
│  │  │  ├─ faq_agent.py
│  │  │  ├─ orchestrator.py
│  │  │  ├─ payment_agent.py
│  │  │  ├─ policies.py
│  │  │  ├─ voc_agent.py
│  │  │  ├─ prompts
│  │  │  │  ├─ __init__.py
│  │  │  │  ├─ bug_prompt.py
│  │  │  │  ├─ faq_prompt.py
│  │  │  │  ├─ orchestrator_prompt.py
│  │  │  │  ├─ payment_prompt.py
│  │  │  │  └─ system_prompt.py
│  │  │  └─ response
│  │  │     ├─ __init__.py
│  │  │     ├─ final_response.py
│  │  │     └─ fixed_responses.py
│  │  ├─ memory
│  │  │  ├─ __init__.py
│  │  │  └─ chat_history.py
│  │  ├─ notifications
│  │  │  ├─ __init__.py
│  │  │  ├─ dispatcher.py
│  │  │  └─ slack.py
│  │  ├─ observability
│  │  │  ├─ __init__.py
│  │  │  ├─ error_classifier.py
│  │  │  ├─ langsmith.py
│  │  │  └─ logger.py
│  │  ├─ repository
│  │  │  ├─ __init__.py
│  │  │  ├─ account_repository.py
│  │  │  ├─ analysis_repository.py
│  │  │  ├─ base.py
│  │  │  ├─ draft_repository.py
│  │  │  ├─ failed_query_repository.py
│  │  │  ├─ final_response_repository.py
│  │  │  ├─ operation_log_repository.py
│  │  │  ├─ safety_repository.py
│  │  │  ├─ ticket_repository.py
│  │  │  └─ voc_repository.py
│  │  ├─ retrieval
│  │  │  ├─ __init__.py
│  │  │  ├─ cache_store.py
│  │  │  ├─ cache_tools.py
│  │  │  ├─ embeddings.py
│  │  │  ├─ retriever.py
│  │  │  ├─ vector_store.py
│  │  │  └─ vector_tools.py
│  │  ├─ safety
│  │  │  ├─ __init__.py
│  │  │  └─ safety_layer.py
│  │  ├─ service
│  │  │  ├─ __init__.py
│  │  │  ├─ account_service.py
│  │  │  └─ chatbot_service.py
│  │  ├─ tools
│  │  │  ├─ __init__.py
│  │  │  ├─ CLAUDE.md
│  │  │  ├─ db_tools.py
│  │  │  └─ registry.py
│  │  └─ utils
│  │     ├─ __init__.py
│  │     ├─ errors.py
│  │     └─ passwords.py
│  ├─ common
│  │  ├─ db
│  │  │  └─ connection.py
│  │  ├─ documents_processing
│  │  │  ├─ __init__.py
│  │  │  ├─ chunking.py
│  │  │  ├─ cli.py
│  │  │  ├─ embed.py
│  │  │  ├─ normalize.py
│  │  │  ├─ pipeline.py
│  │  │  ├─ repository.py
│  │  │  └─ types.py
│  │  ├─ llm
│  │  │  └─ client.py
│  │  ├─ observability
│  │  │  ├─ __init__.py
│  │  │  └─ langsmith.py
│  │  └─ utils
│  │     ├─ config.py
│  │     └─ logger.py
│  ├─ dashboard
│  │  ├─ ai.py
│  │  ├─ run.py
│  │  ├─ api
│  │  │  └─ main.py
│  │  ├─ frontend
│  │  │  ├─ app.py
│  │  │  ├─ session_state.py
│  │  │  ├─ components
│  │  │  │  ├─ chart_box.py
│  │  │  │  └─ data_table.py
│  │  │  └─ pages
│  │  │     ├─ 1_운영_현황.py
│  │  │     ├─ 2_리스크_분석.py
│  │  │     ├─ 3_응답_품질.py
│  │  │     └─ 4_주간_보고서.py
│  │  ├─ util
│  │  │  ├─ __init__.py
│  │  │  ├─ metrics.py
│  │  │  ├─ text.py
│  │  │  └─ views.py
│  │  └─ workflow
│  │     ├─ __init__.py
│  │     ├─ graph.py
│  │     ├─ nodes.py
│  │     ├─ state.py
│  │     └─ weekly_report
│  │        ├─ __init__.py
│  │        ├─ graph.py
│  │        ├─ pdf.py
│  │        ├─ scheduler.py
│  │        ├─ service.py
│  │        ├─ slack.py
│  │        └─ state.py
│  └─ operation
│     ├─ run.py
│     ├─ api
│     │  └─ main.py
│     ├─ frontend
│     │  ├─ app.py
│     │  ├─ components
│     │  │  ├─ answer_panel.py
│     │  │  ├─ safety_result_box.py
│     │  │  └─ ticket_card.py
│     │  ├─ pages
│     │  │  ├─ 1_문의_목록.py
│     │  │  ├─ 2_답변_생성.py
│     │  │  └─ 3_검수_결과.py
│     │  └─ state
│     │     └─ session_state.py
│     └─ workflow
│        ├─ __init__.py
│        ├─ graph.py
│        ├─ nodes.py
│        ├─ prompts.py
│        └─ state.py
└─ tests
   ├─ __init__.py
   ├─ chatbot
   │  ├─ __init__.py
   │  ├─ _hybrid_retrieval_cases.py
   │  ├─ _orchestrator_routing_cases.py
   │  ├─ _persistence_evidence_cases.py
   │  ├─ test_account_service.py
   │  ├─ test_chatbot_flow.py
   │  ├─ test_db_schema.py
   │  ├─ test_payment_flow.py
   │  └─ test_rag_pipeline.py
   ├─ common
   │  ├─ test_db_connection.py
   │  └─ test_documents_processing.py
   ├─ dashboard
   │  └─ test_dashboard_service.py
   └─ operation
      ├─ test_operation_workflow_graph_image.py
      ├─ test_workflow_full.py
      └─ test_workflow_unit.py
```

## 기술 스택

- API: FastAPI, Uvicorn
- UI: Streamlit
- 워크플로우: LangGraph
- LLM 연동: `langchain-openai`
- 데이터 저장소: PostgreSQL, pgvector
- 대시보드 시각화: Pandas, Plotly
- 스케줄링: APScheduler
- 알림: Slack SDK
- 보고서 생성: `xhtml2pdf`
- 테스트: Pytest

## 환경 변수

기본 환경 변수는 `.env.example`에 정의되어 있습니다. 로컬 실행 시 `.env`를 준비하면 됩니다.

필수 항목:

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
