# Notion용 DB 요약

`db_info.md`와 `descriptions.md`를 Notion에서 읽기 쉽게 다시 정리한 문서다. 이 문서는 **2026-05-26 기준 현재 live DB 상태**를 반영한다.

## 1. 현재 상태 한눈에 보기

| 항목 | 값 |
| --- | --- |
| DBMS | PostgreSQL |
| 버전 | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)` |
| 호스트 | `100.97.235.15` |
| 포트 | `5432` |
| 데이터베이스 | `game_cs` |
| 사용자 | `game_cs_user` |
| 스키마 | `public` |
| 확장 | `plpgsql 1.0`, `vector 0.6.0` |
| 전체 public 테이블 수 | 40 |
| 전체 public 컬럼 수 | 330 |

## 2. 시스템 범위

- 유저/계정 마스터: `community_users`, `game_accounts`
- 고객 문의: `qa_ticket`
- 운영 근거 데이터: `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- 답변 생성 워크플로우: `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`
- 운영/모니터링: `failed_queries`, `notification_logs`, `admin_event_logs`, `insight`, `voc_feedback`
- 문서/RAG 저장소: `documents`, `documents_chunks`, `documents_embeddings`
- 템플릿/원본 보존용 백업 테이블: 각 메인 테이블의 `_ex` 버전

## 3. 현재 DB 운용 해석

현재 DB는 **메인 운영 테이블 20개 + 템플릿/백업용 `_ex` 테이블 20개**로 구성되어 있다.

- 메인 테이블은 현재 축소(reduced) 데이터셋 상태를 반영한다.
- `_ex` 테이블은 원본 규모 또는 샘플 데이터를 보관하는 템플릿 역할을 한다.
- `docs/data_generation/repopulate_reduced_dataset.py`는 이 `_ex` 테이블들을 참조해 메인 7개 테이블을 다시 채운다.

## 4. 메인 테이블 현재 건수

아래 건수는 2026-05-26 기준 `pg_stat_user_tables.n_live_tup` 확인값이다.

| 테이블 | 현재 건수 | 설명 |
| --- | ---: | --- |
| `admin_event_logs` | 0 | 운영/관리 이벤트 로그 |
| `answer_draft` | 0 | 답변 초안 |
| `community_users` | 630 | 축소 유저 마스터 |
| `documents` | 1,201 | 정책/공지/가이드 문서 |
| `documents_chunks` | 0 | 현재 메인 chunk 적재 없음 |
| `documents_embeddings` | 0 | 현재 메인 embedding 적재 없음 |
| `evidence_docs` | 0 | 근거 문서 연결 결과 |
| `failed_queries` | 0 | 실패 질의 로그 |
| `final_response` | 0 | 최종 응답 |
| `gacha_logs` | 180 | 가챠 이력 |
| `game_accounts` | 630 | 축소 게임 계정 마스터 |
| `insight` | 0 | 인사이트 분석 결과 |
| `item_delivery_logs` | 140 | 아이템 지급/미지급 이력 |
| `notification_logs` | 0 | 알림 발송 로그 |
| `payments` | 320 | 결제 이력 |
| `qa_ticket` | 950 | 축소 문의 데이터 |
| `refunds` | 55 | 환불 이력 |
| `safety_results` | 0 | 안전성 점검 결과 |
| `ticket_analysis` | 0 | 문의 분석 결과 |
| `voc_feedback` | 0 | VOC 피드백 |

## 5. `_ex` 템플릿 테이블 현재 건수

이 테이블들은 원본 규모 또는 예시 데이터를 유지하는 템플릿 성격의 보조 테이블이다.

| 테이블 | 현재 건수 | 용도 |
| --- | ---: | --- |
| `admin_event_logs_ex` | 3 | 운영 로그 예시 |
| `answer_draft_ex` | 329 | 답변 초안 예시 |
| `community_users_ex` | 6,288 | 원본 유저 마스터 기준 |
| `documents_ex` | 1,201 | 원본 문서 기준 |
| `documents_chunks_ex` | 3,864 | 원본 chunk 기준 |
| `documents_embeddings_ex` | 3,864 | 원본 embedding 기준 |
| `evidence_docs_ex` | 837 | 근거 문서 예시 |
| `failed_queries_ex` | 11 | 실패 질의 예시 |
| `final_response_ex` | 311 | 최종 응답 예시 |
| `gacha_logs_ex` | 5 | 가챠 예시 |
| `game_accounts_ex` | 6,288 | 원본 계정 기준 |
| `insight_ex` | 5 | 인사이트 예시 |
| `item_delivery_logs_ex` | 5 | 지급 로그 예시 |
| `notification_logs_ex` | 2 | 알림 로그 예시 |
| `payments_ex` | 11 | 결제 예시 |
| `qa_ticket_ex` | 9,349 | 원본 문의 기준/보강용 seed |
| `refunds_ex` | 5 | 환불 예시 |
| `safety_results_ex` | 287 | 안전성 점검 예시 |
| `ticket_analysis_ex` | 351 | 문의 분석 예시 |
| `voc_feedback_ex` | 43 | VOC 예시 |

## 6. 축소 데이터셋 핵심 7개 테이블

현재 reduced dataset에서 직접 운용되는 핵심 테이블은 아래 7개다.

| 테이블 | 목표/현재 건수 | 역할 |
| --- | ---: | --- |
| `community_users` | 630 | 문의를 소유하는 유저 마스터 |
| `game_accounts` | 630 | 게임 계정 마스터 |
| `qa_ticket` | 950 | 실제 문의/게시글 중심 테이블 |
| `payments` | 320 | 결제 문의 설명용 운영 근거 |
| `refunds` | 55 | 환불 문의 설명용 운영 근거 |
| `item_delivery_logs` | 140 | 아이템 미지급/지급 지연 설명용 운영 근거 |
| `gacha_logs` | 180 | 가챠 불만/확률 문의 설명용 운영 근거 |

핵심 해석:

- `qa_ticket`가 본체다.
- 나머지 6개 테이블은 문의가 왜 발생했는지 설명하는 운영 근거 데이터다.
- 현재 워크플로우 산출물 테이블은 비어 있고, 질문/응답 파이프라인을 돌리면 다시 채워지는 구조다.

## 7. 주요 관계 요약

- `community_users.user_id`는 `game_accounts`, `qa_ticket`의 부모 키다.
- `game_accounts.account_id`는 `payments`, `gacha_logs`, `item_delivery_logs`, `qa_ticket.account_id`와 연결된다.
- `qa_ticket.account_id`는 nullable이며, 계정이 없는 커뮤니티 문의도 허용한다.
- `payments.payment_id`는 `refunds.payment_id`, `item_delivery_logs.payment_id`와 연결된다.
- `qa_ticket`는 답변 워크플로우에서 `ticket_analysis -> answer_draft -> safety_results/final_response`로 이어진다.
- 문서 저장소는 `documents -> documents_chunks -> documents_embeddings` 순으로 이어진다.

## 8. 운영 워크플로우 읽기/쓰기 맵

| 단계 | 주요 테이블 |
| --- | --- |
| 문의 로드 | `qa_ticket`, `community_users`, `game_accounts` |
| 결제 컨텍스트 조회 | `payments`, `game_accounts` |
| 환불 컨텍스트 조회 | `refunds`, `payments`, `game_accounts` |
| 아이템 지급 조회 | `item_delivery_logs`, `game_accounts` |
| 가챠 컨텍스트 조회 | `gacha_logs`, `game_accounts` |
| VOC/패턴 조회 | `insight`, `voc_feedback` |
| 정책/공지 조회 | `documents` |
| RAG 검색 | `documents`, `documents_chunks`, `documents_embeddings` |
| 워크플로우 결과 기록 | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries`, `admin_event_logs` |

## 9. 현재 상태에서 주의할 점

### 9.1 현재 메인 RAG 저장소는 비어 있음

- `documents`는 1,201건 존재한다.
- 하지만 현재 메인 `documents_chunks`, `documents_embeddings`는 0건이다.
- chunk/embedding 예시는 `_ex` 테이블에 남아 있다.

따라서 현재 메인 DB만 보면 문서 본문은 있지만 검색용 chunk/embedding은 비어 있는 상태다.

### 9.2 워크플로우 결과 테이블은 비어 있음

현재 다음 메인 테이블은 0건이다.

- `ticket_analysis`
- `answer_draft`
- `evidence_docs`
- `safety_results`
- `final_response`
- `failed_queries`
- `admin_event_logs`
- `notification_logs`
- `insight`
- `voc_feedback`

즉, reduced dataset는 현재 **입력 데이터는 채워져 있고, 워크플로우 결과물은 초기화된 상태**로 보는 것이 맞다.

### 9.3 `_ex` 테이블은 보조 템플릿으로 취급해야 함

- `_ex` 테이블은 현재 운영 대상이 아니라 재생성/참조용 기준 데이터다.
- 분석이나 데모에서 메인 테이블과 `_ex` 테이블을 혼동하면 안 된다.
- 발표/문서에서는 “현재 운영용 메인 테이블”과 “템플릿/백업 테이블”을 구분해서 설명하는 것이 안전하다.

## 10. 데이터 생성 관련 참조

현재 reduced dataset의 설계와 재생성 로직은 `docs/data_generation/` 아래 문서를 기준으로 본다.

- `docs/data_generation/plan.md`
  - 축소 범위, 목표 건수, hard case quota, 테이블별 생성 정책
- `docs/data_generation/paper_description.md`
  - 논문 기반 설계 근거, seed 기반 확장, hard case 보강, privacy/style 고려
- `docs/data_generation/repopulate_reduced_dataset.py`
  - `_ex` 테이블을 이용해 메인 7개 테이블을 다시 채우는 스크립트
- `docs/data_generation/ppt_data_generation_narrative.md`
  - 발표용 방법론/도메인 설명

## 11. 메인 스키마 ERD

```smalltalk
Table community_users {
  user_id int [pk]
  email varchar
  nickname varchar
  created_at datetime
  user_status varchar
  last_login_at datetime
  password_hash text
  password_updated_at datetime
}

Table game_accounts {
  account_id int [pk]
  user_id int [ref: > community_users.user_id]
  game_name varchar
  uid varchar
  server_region varchar
  progression_level int
  account_status varchar
  created_at datetime
}

Table qa_ticket {
  ticket_id int [pk]
  account_id int [ref: > game_accounts.account_id, null]
  user_id int [ref: > community_users.user_id]
  title varchar
  raw_query text
  source_type varchar
  status varchar
  inquiry_created_at datetime
  session_id int
  responder_type varchar
}

Table payments {
  payment_id int [pk]
  account_id int [ref: > game_accounts.account_id]
  product_name varchar
  product_type varchar
  amount decimal
  currency varchar
  payment_method varchar
  payment_status varchar
  transaction_id varchar
  paid_at datetime
}

Table refunds {
  refund_id int [pk]
  payment_id int [ref: > payments.payment_id]
  refund_status varchar
  refund_reason text
  requested_at datetime
  processed_at datetime
}

Table item_delivery_logs {
  delivery_id int [pk]
  payment_id int [ref: > payments.payment_id, null]
  account_id int [ref: > game_accounts.account_id]
  source_type varchar
  item_name varchar
  quantity int
  delivery_status varchar
  expected_at datetime
  delivered_at datetime
}

Table gacha_logs {
  gacha_id int [pk]
  account_id int [ref: > game_accounts.account_id]
  banner_name varchar
  item_name varchar
  item_type varchar
  rarity varchar
  pity_count int
  pulled_at datetime
}

Table ticket_analysis {
  analysis_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  category varchar
  responder_type varchar
  enriched_query text
  risk_level varchar
  sentiment varchar
  routing_target varchar
  summary text
  analyzed_at datetime
}

Table answer_draft {
  draft_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  analysis_id int [ref: > ticket_analysis.analysis_id]
  draft_text text
  prompt_version varchar
  created_at datetime
}

Table evidence_docs {
  evidence_id int [pk]
  draft_id int [ref: > answer_draft.draft_id]
  source_type varchar
  source_id varchar
  evidence_text text
  relevance_score float
  retrieval_rank int
}

Table safety_results {
  safety_id int [pk]
  draft_id int [ref: > answer_draft.draft_id]
  hallucination_score float
  toxicity_score float
  policy_violation_score float
  factuality_score float
  checked_at datetime
  safety_action varchar
  safety_reason varchar
  retry_count int
}

Table final_response {
  response_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  draft_id int [ref: > answer_draft.draft_id, null]
  final_text text
  safety_action varchar
  created_at datetime
}
```

## 12. 문서/RAG 스키마 ERD

```smalltalk
Table documents {
  documents_id varchar [pk]
  source_type varchar
  category varchar
  title varchar
  raw_content text
  source_url varchar
  published_at datetime
  updated_at datetime
}

Table documents_chunks {
  chunk_id varchar [pk]
  document_id varchar [ref: > documents.documents_id]
  chunk_text text
  chunk_order int
  token_count int
  created_at datetime
}

Table documents_embeddings {
  embedding_id varchar [pk]
  chunk_id varchar [ref: > documents_chunks.chunk_id]
  embedding_vector vector
  embedding_model varchar
  source_type varchar
  category varchar
  created_at datetime
}
```

## 13. 데이터 소스 메모

| 소스 | 대상 테이블 | 메모 |
| --- | --- | --- |
| `data/processed/community_users.csv` | `community_users` | 원본 9,221행에서 `user_id` 기준 upsert, 결과적으로 6,288 distinct user |
| `data/processed/qa_ticket.csv` | `qa_ticket` | CSV 헤더에 `source_type`가 중복으로 존재하며 적재 노트북은 첫 번째 값을 사용 |
| `notebooks/insert_processed_data.ipynb` | `community_users`, `game_accounts`, `qa_ticket` | `qa_ticket.account_id`와 `user_id`의 non-null 매핑으로 `game_accounts`를 구성 |
| `notebooks/generate_operation_workflow_sample_data.ipynb` | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight`, `voc_feedback` | 운영 컨텍스트용 샘플 데이터 생성 |
| `docs/data_generation/repopulate_reduced_dataset.py` | `community_users`, `game_accounts`, `qa_ticket`, `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` | `_ex` 테이블을 참조해 reduced dataset 재구성 |
