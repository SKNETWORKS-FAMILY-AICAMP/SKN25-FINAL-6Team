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

## 출력 데이터

`operation/`에서 최종적으로 다루는 핵심 산출물은 아래다.

- `ticket_analysis`
- `answer_draft`
- `evidence_docs`
- `safety_results`
- `approval_result`
- `human_review_request` 또는 `final_outcome`

STEP1과 STEP2는 `ticket_analysis`, `answer_draft`, `evidence_docs`를 만든다. Approval Gate는 이를 검토해 `safety_results`와 최종 승인 결과를 만든다.

## RAG 기준

STEP2는 평면 문서 리스트가 아니라 `docs/ddl.md`의 Vector DB 스키마와 같은 3계층을 사용한다.

1. `documents`: 원문과 메타데이터 저장
2. `documents_chunks`: 검색용 chunk 저장
3. `documents_embeddings`: chunk별 벡터 저장

실제 retrieval 흐름은 `documents_chunks`를 기준으로 후보를 찾고, `document_id`로 `documents`와 조인해 원문과 메타데이터를 복원하며, 필요하면 `documents_embeddings`로 vector similarity를 계산해 재정렬하는 방식이다.

## Agent 책임 분리

- `step12agent/`: STEP1, STEP2
- `approvalagent/`: Approval Gate

상위 `operation/` 문서는 전체 파이프라인 기준을 설명하고, 세부 책임과 프롬프트 및 tool 설계는 각 하위 디렉터리 문서에서 다룬다.

## Middleware 기준

현재 `operation/` 문서 기준의 우선순위는 아래와 같다.

### 1. Human-in-the-loop

- 적용 위치: `approvalagent`
- 목적: 승인 결과가 실제 운영 액션이나 human review 요청으로 이어지기 전에 사람 확인을 넣기 위함
- 기본 방향:
  - 1차 구현은 `HumanInTheLoopMiddleware`
  - 더 복잡한 승인 UX가 필요해지면 LangGraph `interrupt`로 확장

즉 현재 문서 기준은 `middleware`를 기본값으로 두고, `interrupt`는 확장 옵션으로 본다.

### 2. Model retry

- 적용 위치: `step12agent`, `approvalagent`
- 이유: 분류, 초안 생성, safety scoring, approval decision은 provider 오류나 timeout의 영향을 받을 수 있다.

### 3. Model fallback

- 적용 위치: `step12agent`, `approvalagent`
- 이유: 주 모델 장애 시 운영 파이프라인 전체가 멈추지 않게 하기 위함

### 4. Tool retry

- 적용 위치: retrieval tool, embedding tool, Vector DB/ChromaDB 접근 tool
- 이유: 임베딩 생성, Vector DB 조회, 외부 API 호출은 일시 실패 가능성이 있다.

### 5. PII detection

- 적용 위치: `step12agent` 입력 전처리, `approvalagent` 최종 승인 전
- 이유: `qa_ticket.raw_content`, `account_context.email`, UID, 거래 정보 등 민감 데이터가 들어온다.

### 6. Tool call limit / Model call limit

- 적용 위치: `operation` 공통
- 이유: 무한 루프나 과도한 재시도로 비용과 지연이 커지는 것을 막기 위함

## 실제 적용 우선순위

1. `approvalagent`에 Human-in-the-loop
2. `step12agent`, `approvalagent`에 Model retry
3. `step12agent`, `approvalagent`에 Model fallback
4. retrieval/embedding tool에 Tool retry
5. operation 공통으로 PII detection
6. operation 공통으로 call limit

## 현재 구현 상태

- `runners/run_operation.py`와 `runners/run_dashboard.py`는 `operation.agent`를 import하도록 작성되어 있다.
- `step12agent`는 문서 기준과 payload 기준이 먼저 정리된 상태다.
- `approvalagent`는 `create_agent(...)` 베이스와 approval tools 뼈대가 있다.
- 다만 middleware, retry, fallback은 아직 문서 수준의 권장안이며 실제 연결은 남아 있다.

즉 이 디렉터리는 전체 설계 기준과 payload 구조는 고정되어 있지만, 실행 로직은 아직 확장 중인 단계로 보는 것이 맞다.

## 관련 파일

- 루트 개요: `README.md`
- 운영 플로우: `docs/operation_dashboard.md`
- 데이터 스키마: `docs/ddl.md`
- seed 입력: `data/seed_payload.py`
- STEP1/2 문서: `operation/step12agent/README.md`
- Approval Gate 문서: `operation/approvalagent/README.md`
- 실행 진입점: `runners/run_operation.py`
