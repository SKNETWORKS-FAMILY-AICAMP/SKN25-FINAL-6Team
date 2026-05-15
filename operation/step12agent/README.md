# Step12 Agent

`step12agent/`는 운영 자동화 파이프라인의 STEP1과 STEP2를 담당한다. 문의 분류, 라우팅, RAG 검색, 답변 초안 생성을 이 범위에서 처리한다.

## 범위

1. STEP1: 문의 유형 분류와 Query Routing
2. STEP2: RAG 검색과 답변 초안 생성

산출물은 다음 3가지다.

- `ticket_analysis`
- `answer_draft`
- `evidence_docs`

## 입력

현재 입력은 `data/seed_payload.py`의 `FIRST_INPUT_PAYLOAD`를 사용한다.

- `qa_ticket`
- `account_context`
- `operation_logs`
- `knowledge_base`

`account_context`는 DDL의 실제 테이블명이 아니라 `QA_ticket.user_id`, `QA_ticket.account_id`를 기준으로 `community_users`와 `game_accounts`를 병합한 파생 입력이다.

`knowledge_base`는 Vector DB 스키마를 payload로 옮긴 구조이며 아래 3개 컬렉션으로 구성된다.

- `knowledge_base.documents`
- `knowledge_base.documents_chunks`
- `knowledge_base.documents_embeddings`

생성 로직은 `build_account_context_from_ddl()`, `build_knowledge_base_from_vector_ddl()`, `build_first_input_payload()`에 있다.

## STEP1 책임

STEP1은 문의 원문과 운영 로그를 보고 아래 필드를 만든다.

- `category`
- `risk_level`
- `sentiment`
- `routing_target`
- `summary`

판단 근거는 `qa_ticket`, 계정 정보, 결제/환불/지급 로그다.

## STEP2 책임

STEP2는 STEP1 결과를 바탕으로 Vector DB payload를 검색하고 근거 기반 초안을 만든다.

- `knowledge_base.documents_chunks`에서 관련 chunk 검색
- `document_id`로 `knowledge_base.documents` 원문과 메타데이터 조인
- 필요 시 `knowledge_base.documents_embeddings`로 vector similarity 반영
- 근거 목록 정리
- 답변 초안 생성

결과는 `answer_draft`, `evidence_docs`에 매핑된다.

## RAG 로직

의도된 흐름은 아래와 같다.

1. STEP1에서 `category`, `routing_target`, `summary`를 생성한다.
2. STEP2가 `qa_ticket` 원문과 STEP1 결과, 운영 로그를 조합해 검색 질의를 만든다.
3. BM25로 `documents_chunks.chunk_text` 후보를 추린다.
4. 가능하면 query embedding을 만들고 `documents_embeddings`에서 vector similarity를 계산한다.
5. lexical 점수와 vector 점수를 합쳐 최종 chunk를 고른다.
6. 선택된 chunk를 `document_id` 기준으로 `documents`와 조인해 근거 문맥을 복원한다.
7. 상위 근거만 `evidence_docs`로 저장하고, 그 근거만 사용해 `answer_draft`를 생성한다.

### 검색 대상

- 원문 저장소: `knowledge_base.documents`
- 검색 단위: `knowledge_base.documents_chunks`
- 벡터 인덱스: `knowledge_base.documents_embeddings`
- 결과 저장 단위: `evidence_docs`

### 검색 방식

현재 `tools.py`에 `BM25Okapi` import가 있으므로 1차 구현은 BM25 기반 retrieval이 가장 단순하다. 이후에는 `EMBEDDING_MODEL`을 사용한 vector retrieval을 추가해 hybrid retrieval로 확장한다.

- 1차 후보 검색: BM25로 chunk 상위 N개 검색
- 2차 확장: query embedding 생성 후 `documents_embeddings`에서 vector similarity search 수행
- 최종 선택: BM25 점수와 vector 유사도를 함께 참고해 상위 chunk만 채택

관련 설정은 아래를 따른다.

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `EMBEDDING_MODEL`
- `VECTOR_COLLECTION`
- `RETRIEVAL_TOP_K`

### 질의 생성 기준

RAG 질의는 사용자 원문만 복사하지 않고 운영 맥락까지 포함해야 한다.

- `qa_ticket.title`
- `qa_ticket.raw_content`
- STEP1의 `category`
- STEP1의 `summary`
- 필요 시 `payment_status`, `refund_status`, `delivery_status`

예를 들어 결제 성공 이후 지급 실패 문의라면 질의는 자연어 한 문장보다 `payment success item delivery fail refund pending` 같은 구조화된 힌트를 포함하는 편이 낫다.

### 근거 선택 기준

- 문의 카테고리와 직접 관련 있는 문서인가
- 문서 메타데이터와 chunk 텍스트가 모두 일치하는가
- 처리 정책인지, 단순 안내인지 구분되는가
- 중복 chunk를 과도하게 뽑지 않았는가

최종적으로 `RETRIEVAL_TOP_K` 개수만 남기고 각 항목을 `source_type`, `source_id`, `evidence_text`, `relevance_score`, `retrieval_rank`에 매핑하는 형태가 적절하다.

### 초안 생성 규칙

- 검색된 근거 범위 안에서만 안내한다.
- 환불, 재지급, 수동 처리 가능 여부는 로그와 정책 근거가 있을 때만 명시한다.
- 근거가 약하면 확정 표현 대신 확인 필요 상태로 표현한다.
- `routing_target=urgent_alert`이면 자동 답변보다 운영 검토 우선 흐름을 반영한다.

목표는 그럴듯한 답변이 아니라 근거가 명확한 운영 초안이다.

## 현재 상태

- `prompts.py`: STEP1_SYSTEM, STEP2_SYSTEM, STEP2_CONTEXT_TEMPLATE 구현 완료
- `tools.py`: BM25 / vector similarity / hybrid retrieval, `record_ticket_analysis` @tool, `make_retrieve_evidence_tool` 팩토리 구현 완료
- `agent.py`: Step12State, step1_node, step2_node, StateGraph(START→step1→step2→END) 구현 완료

STEP1/STEP2 베이스라인 구현이 완료된 상태다. 실행 진입점은 `runners/run_operation.py`다.
