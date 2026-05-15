# Game CS Automation System

루트 구조는 `chatbot`, `operation`, `dashboard` 세 모듈로 나뉜다.

기본 파이프라인은 `operation`을 먼저 실행하고 그 결과를 `dashboard`로 넘기는 방식이다.

seed payload는 DDL 기준 row를 애플리케이션 입력 형태로 조립한다.

- `account_context`: `community_users`와 `game_accounts`를 병합한 파생 객체
- `knowledge_base`: Vector DB 스키마인 `documents`, `documents_chunks`, `documents_embeddings`를 그대로 담은 RAG 입력
