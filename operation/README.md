# Operation

`operation/`은 운영 자동화 파이프라인의 STEP1, STEP2, Approval Gate를 담당한다. 문의 분석, RAG 근거 검색, 답변 초안 생성, 승인 판단까지를 이 범위에서 처리한다.

## 역할

1. STEP1: 문의 유형 분류, 위험도 판단, 라우팅 결정
2. STEP2: RAG 기반 근거 검색과 답변 초안 생성
3. Approval Gate: 초안 검토, 안전성 확인, human review 필요 여부 판단

STEP3와 관측 지표 집계는 `dashboard/` 범위다.

## 입력 데이터

현재 기준 입력은 `data/seed_payload.py`의 `FIRST_INPUT_PAYLOAD`를 사용한다.

- `qa_ticket`: `QA_ticket` seed row
- `account_context`: `QA_ticket.user_id`, `QA_ticket.account_id`를 기준으로 `community_users`, `game_accounts`를 병합한 파생 객체
- `operation_logs`: `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- `knowledge_base.documents`: Vector DB 원문 문서
- `knowledge_base.documents_chunks`: 검색 단위 chunk
- `knowledge_base.documents_embeddings`: chunk별 임베딩

`account_context`는 `build_account_context_from_ddl()`에서 조립하고, `knowledge_base`는 `build_knowledge_base_from_vector_ddl()`에서 조립한다. `build_first_input_payload()`가 이 둘을 합쳐 최종 입력 payload를 만든다.

## RAG 기준

STEP2는 더 이상 평면 `policy_documents` 리스트를 직접 읽지 않는다. `docs/ddl.md`의 Vector DB 스키마에 맞춰 다음 3계층을 사용한다.

1. `documents`: 원문과 메타데이터 저장
2. `documents_chunks`: 검색용 chunk 저장
3. `documents_embeddings`: chunk별 벡터 저장

실제 retrieval 흐름은 `documents_chunks`를 기준으로 후보를 찾고, `document_id`로 `documents`와 조인해 원문/메타데이터를 복원하며, 필요하면 `documents_embeddings`로 vector similarity를 계산해 재정렬하는 방식이다.

## 현재 구현 상태

- `runners/run_operation.py`와 `runners/run_dashboard.py`는 `operation.agent`를 import하도록 작성되어 있다.
- 하지만 현재 `operation/` 최상위의 실제 실행 로직은 아직 스켈레톤에 가깝다.
- 따라서 이 디렉터리는 문서 구조와 payload, 에이전트 책임을 먼저 고정하는 단계로 보는 것이 맞다.

## 관련 파일

- 루트 개요: `README.md`
- 운영 플로우: `docs/operation_dashboard.md`
- 데이터 스키마: `docs/ddl.md`
- seed 입력: `data/seed_payload.py`
- 실행 진입점: `runners/run_operation.py`
