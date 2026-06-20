# Test Strategy

이 문서는 현재 저장소 기준으로 `pytest`로 돌려야 하는 테스트 요소를 `단위테스트`, `통합테스트`, `실환경 연동 테스트`, `수동/탐색 스크립트`로 나눠 정리한다.

## 분류 기준

- 단위테스트
  - 순수 함수, 단일 서비스, 라우팅 규칙, 데이터 변환 로직을 검증한다.
  - DB, Slack, LLM, GitHub, Redis 같은 외부 의존성은 실제로 호출하지 않는다.
- 통합테스트
  - 여러 모듈이나 레이어를 함께 묶어 실행한다.
  - 다만 현재 저장소에서는 외부 시스템 경계는 대부분 `monkeypatch`로 대체한다.
- 실환경 연동 테스트
  - 실제 DB 또는 실제 LLM/API 환경변수에 의존한다.
  - 로컬 검증용으로만 제한적으로 돌리는 편이 안전하다.
- 수동/탐색 스크립트
  - 파일명이 `test_*.py`여도 자동화된 `pytest` 테스트라기보다 데이터 확인, 샘플 조회, 드라이런에 가깝다.
  - 기본 테스트 세트에서는 제외하는 편이 맞다.

## 권장 실행 세트

### 1. 빠른 단위테스트

```powershell
pytest `
  apps\tests\chatbot_tests\test_account_service.py `
  apps\tests\chatbot_tests\test_cache_store.py `
  apps\tests\chatbot_tests\test_chat_history.py `
  apps\tests\chatbot_tests\test_multihop_retrieval.py `
  apps\tests\chatbot_tests\test_payment_flow.py `
  apps\tests\cs-auto_tests\test_api_contract.py `
  apps\tests\weekly_report_tests\test_weekly_report_ai.py `
  apps\tests\weekly_report_tests\test_weekly_report_build.py `
  apps\tests\weekly_report_tests\test_weekly_report_db.py `
  apps\tests\weekly_report_tests\test_weekly_report_slack.py `
  apps\tests\weekly_report_tests\test_weekly_report_utils.py `
  common\tests\test_documents_processing.py `
  common\tests\test_retrieval_routing.py
```

### 2. monkeypatch 기반 통합테스트 포함

```powershell
pytest `
  apps\tests\chatbot_tests\test_chatbot_flow.py `
  apps\tests\chatbot_tests\test_rag_pipeline.py `
  apps\tests\cs-auto_tests\test_analysis_agent.py `
  apps\tests\cs-auto_tests\test_answer_agent.py `
  apps\tests\weekly_report_tests\test_weekly_report_pipeline.py
```

### 3. 실환경 연동 테스트

```powershell
pytest common\tests\test_db_connection.py
pytest apps\tests\chatbot_tests\test_db_schema.py
```

추가 live 테스트:

```powershell
$env:CS_AUTO_RUN_LIVE_TESTS="1"
pytest apps\tests\cs-auto_tests\test_answer_agent.py -k live
```

## 영역별 분류

### Chatbot

#### 단위테스트

- [apps/tests/chatbot_tests/test_account_service.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_account_service.py)
  - 로그인 서비스가 입력 이메일 값을 어떻게 넘기는지 검증한다.
  - 외부 로그인 검증 함수는 `patch`로 대체한다.
- [apps/tests/chatbot_tests/test_cache_store.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_cache_store.py)
  - 메모리 캐시, Redis fallback, TTL, key prefix 동작을 검증한다.
  - Redis는 fake 객체로 대체된다.
- [apps/tests/chatbot_tests/test_chat_history.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_chat_history.py)
  - 대화 이력 trimming, summary 병합 규칙을 검증한다.
- [apps/tests/chatbot_tests/test_multihop_retrieval.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_multihop_retrieval.py)
  - 멀티홉 판단, intent 추론, routing 규칙을 검증한다.
  - 하단의 수동 실험 함수는 자동 테스트 범위와 분리해서 봐야 한다.
- [apps/tests/chatbot_tests/test_payment_flow.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_payment_flow.py)
  - 결제 에이전트가 사용자 범위로 컨텍스트를 수집하는지 검증한다.
  - DB access는 fake connection으로 대체된다.

#### 통합테스트

- [apps/tests/chatbot_tests/test_chatbot_flow.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_chatbot_flow.py)
  - `build_state`, `ticket_preprocess`, `safety_layer`, `final_response`, `dispatcher`까지 이어지는 흐름을 검증한다.
  - 외부 쓰기/알림 함수는 `monkeypatch`로 대체한다.
- [apps/tests/chatbot_tests/test_rag_pipeline.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_rag_pipeline.py)
  - FAQ RAG 파이프라인의 조회, 리랭크, 캐시, evidence 저장, fallback 분기를 함께 검증한다.
  - 실DB/실LLM 없이 파이프라인 조합을 검증하는 성격이다.

#### 실환경 연동 테스트

- [apps/tests/chatbot_tests/test_db_schema.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_db_schema.py)
  - 실제 DB에 접속해 필수 테이블과 auto-generated id 컬럼을 검사한다.
  - `DB_PASSWORD`가 없으면 skip된다.

#### 수동/탐색 스크립트

- [apps/tests/chatbot_tests/test_db_content.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_db_content.py)
  - 문서 테이블에서 샘플 데이터를 조회하는 스크립트다.
  - `pytest` 테스트 함수가 없다.
- [apps/tests/chatbot_tests/test_find_answers.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_find_answers.py)
  - 실제 문서 내용을 키워드로 탐색하는 스크립트다.
- [apps/tests/chatbot_tests/test_chunking_search.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_chunking_search.py)
  - 실제 임베딩 생성과 test table 조회를 수행한다.
  - 자동 테스트보다 분석용 스크립트에 가깝다.
- [apps/tests/chatbot_tests/test_chunking_dryrun.py](/C:/SKN25-FINAL-6Team/apps/tests/chatbot_tests/test_chunking_dryrun.py)
  - 문서 처리 파이프라인 드라이런/재생성 확인용이다.

### CS Auto

#### 단위테스트

- [apps/tests/cs-auto_tests/test_api_contract.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/test_api_contract.py)
  - API contract와 프런트 payload shape를 검증한다.

#### 통합테스트

- [apps/tests/cs-auto_tests/test_analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/test_analysis_agent.py)
  - ticket 분석 결과 조합, routing target 결정, batch 처리 흐름을 검증한다.
  - 주요 의존성은 `monkeypatch`로 대체된다.
- [apps/tests/cs-auto_tests/test_answer_agent.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/test_answer_agent.py)
  - answer agent의 입력 shape, 초안 생성 경로, 단계별 조합 로직을 검증한다.
  - 기본 테스트는 통합 성격이지만 live 테스트는 opt-in이다.

#### 실환경 연동 테스트

- [apps/tests/cs-auto_tests/test_answer_agent.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/test_answer_agent.py)
  - `test_live_answer_agent_with_real_db_and_llm`는 실제 DB와 LLM을 사용한다.
  - `CS_AUTO_RUN_LIVE_TESTS=1`, `DB_*`, `LLM_API_KEY`, `LLM_MODEL`이 필요하다.

#### 수동 테스트 주의

- [apps/tests/cs-auto_tests/test_analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/test_analysis_agent.py)
  - `-s`나 직접 실행을 전제로 한 수동 input 테스트가 포함되어 있다.
  - CI 기본 세트에선 제외하거나 `-k "not manual"` 수준의 관리가 필요하다.

### Weekly Report

#### 단위테스트

- [apps/tests/weekly_report_tests/test_weekly_report_utils.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_utils.py)
  - 비율 계산, 평균 계산, 날짜 유틸 등 순수 함수 검증.
- [apps/tests/weekly_report_tests/test_weekly_report_build.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_build.py)
  - payload/build 레이어의 조합 결과 검증.
- [apps/tests/weekly_report_tests/test_weekly_report_db.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_db.py)
  - DB query 함수이지만 실제 DB 대신 mock connection으로 결과 shape를 검증한다.
  - 현재 저장소 기준으로는 단위테스트에 가깝다.
- [apps/tests/weekly_report_tests/test_weekly_report_ai.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_ai.py)
  - AI 액션/해석 결과 mapping과 fallback을 검증한다.
  - 실제 LLM 호출은 막혀 있다.
- [apps/tests/weekly_report_tests/test_weekly_report_slack.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_slack.py)
  - Slack 업로드 파라미터, 예외 wrapping, retry 규칙을 검증한다.
  - Slack SDK와 DB 기록 함수는 mock 처리된다.

#### 통합테스트

- [apps/tests/weekly_report_tests/test_weekly_report_pipeline.py](/C:/SKN25-FINAL-6Team/apps/tests/weekly_report_tests/test_weekly_report_pipeline.py)
  - `report.run()` 기준으로 metrics, analysis, requests, alerts, AI, PDF, Slack을 한 흐름으로 조합해 검증한다.
  - 외부 의존성은 모두 `monkeypatch`로 차단한다.

### Common Python Package

#### 단위테스트

- [common/tests/test_documents_processing.py](/C:/SKN25-FINAL-6Team/common/tests/test_documents_processing.py)
  - normalize, chunking, pipeline 집계를 fake repository/embedder로 검증한다.
- [common/tests/test_retrieval_routing.py](/C:/SKN25-FINAL-6Team/common/tests/test_retrieval_routing.py)
  - 상태값 조회와 routing helper 분기를 검증한다.

#### 실환경 연동 테스트

- [common/tests/test_db_connection.py](/C:/SKN25-FINAL-6Team/common/tests/test_db_connection.py)
  - 실제 Postgres 연결 후 `SELECT 1`을 수행한다.
  - `DB_PASSWORD`가 없으면 skip된다.

## 운영 권장안

- 기본 개발 루프
  - 빠른 단위테스트 세트를 먼저 돌린다.
- PR 전 검증
  - 단위테스트 + monkeypatch 기반 통합테스트까지 돌린다.
- 배포 전 또는 데이터/환경 점검
  - 실환경 연동 테스트를 별도 실행한다.
- 제외 권장
  - `test_db_content.py`, `test_find_answers.py`, `test_chunking_search.py`, `test_chunking_dryrun.py`는 기본 `pytest` 세트에서 제외하는 편이 안전하다.

## 정리

- 이 저장소의 핵심 자동화 테스트는 `단위테스트 + monkeypatch 기반 통합테스트`다.
- 실DB/실LLM을 직접 때리는 테스트는 일부만 존재하며 opt-in으로 다루는 게 맞다.
- 파일명이 `test_*.py`여도 모두 CI용 테스트는 아니다. 탐색 스크립트는 분리해서 관리해야 한다.
