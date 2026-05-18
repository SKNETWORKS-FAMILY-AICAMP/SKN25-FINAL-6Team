# Game CS Automation System

루트 구조는 `chatbot`, `operation`, `dashboard` 세 모듈로 나뉜다.

기본 파이프라인은 `operation`(STEP1+STEP2) → `approvalagent`(Approval Gate) → `dashboard`(STEP3) 순으로 실행한다.

전체 파이프라인 통합 실행은 `src/runners/run_pipeline.py`가 진입점이다. STEP1+STEP2만 단독 실행은 `src/runners/run_operation.py`, Approval Gate만 단독 실행은 `src/runners/run_approval.py`를 사용한다.

seed payload는 DDL 기준 row를 애플리케이션 입력 형태로 조립한다.

- `account_context`: `community_users`와 `game_accounts`를 병합한 파생 객체
- `knowledge_base`: Vector DB 스키마인 `documents`, `documents_chunks`, `documents_embeddings`를 그대로 담은 RAG 입력
