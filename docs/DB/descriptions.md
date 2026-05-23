# DB Descriptions

작성 기준: `tests/common/test_db_connection.py`에 등록된 접속 정보로 DB에 직접 접속하여 조회한 메타데이터

## 기본 정보

| 항목 | 값 |
| --- | --- |
| DBMS | PostgreSQL |
| PostgreSQL 버전 | 16.13 |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |

## 전체 구성 요약

- 사용자 테이블 수: 20개
- 주요 데이터 성격: 게임 CS/QA 티켓, 유저/계정, 결제/환불, 아이템 지급, 가챠 로그, RAG 문서/임베딩, 답변 생성/검증/운영 로그
- 벡터 검색 지원: `documents_embeddings.embedding_vector` 컬럼과 `ivfflat` cosine 인덱스 사용
- 행 수는 `pg_stat_user_tables.n_live_tup` 기준 추정치이다.

## 테이블 목록

| 테이블 | 추정 행 수 | 설명 |
| --- | ---: | --- |
| `admin_event_logs` | 0 | 운영/관리 워크플로우의 노드, 도구, 라우팅, 오류 이벤트 로그 |
| `answer_draft` | 2 | 티켓 분석 결과를 바탕으로 생성된 답변 초안 |
| `community_users` | 2 | 커뮤니티 사용자 기본 정보 |
| `documents` | 1201 | RAG 검색 원천 문서 |
| `documents_chunks` | 3864 | 문서를 청크 단위로 분할한 텍스트 |
| `documents_embeddings` | 3864 | 문서 청크의 임베딩 벡터 |
| `evidence_docs` | 2 | 답변 초안 생성에 사용된 근거 문서 |
| `failed_queries` | 0 | 검색/처리 실패 질의 기록 |
| `final_response` | 0 | 최종 고객 응답 |
| `gacha_logs` | 2 | 게임 계정의 가챠 이력 |
| `game_accounts` | 2 | 사용자별 게임 계정 정보 |
| `insight` | 2 | 문의/사용자/계정 기반 인사이트 분석 결과 |
| `item_delivery_logs` | 2 | 결제 또는 보상성 아이템 지급 이력 |
| `notification_logs` | 0 | 알림 발송 결과 및 오류 로그 |
| `payments` | 2 | 결제 내역 |
| `qa_ticket` | 2 | 고객 문의/QA 티켓 |
| `refunds` | 2 | 환불 요청 및 처리 내역 |
| `safety_results` | 2 | 답변 초안의 안전성 검증 결과 |
| `ticket_analysis` | 2 | QA 티켓 분류, 감성, 위험도, 라우팅 분석 결과 |
| `voc_feedback` | 0 | VOC 피드백 및 키워드 기록 |

## 주요 관계

| From | To | 관계 |
| --- | --- | --- |
| `game_accounts.user_id` | `community_users.user_id` | 사용자의 게임 계정 |
| `qa_ticket.user_id` | `community_users.user_id` | 사용자가 생성한 문의 |
| `qa_ticket.account_id` | `game_accounts.account_id` | 문의와 게임 계정 연결 |
| `payments.account_id` | `game_accounts.account_id` | 계정별 결제 |
| `refunds.payment_id` | `payments.payment_id` | 결제 건의 환불 |
| `gacha_logs.account_id` | `game_accounts.account_id` | 계정별 가챠 로그 |
| `item_delivery_logs.account_id` | `game_accounts.account_id` | 계정별 아이템 지급 |
| `item_delivery_logs.payment_id` | `payments.payment_id` | 결제 기반 아이템 지급 |
| `ticket_analysis.ticket_id` | `qa_ticket.ticket_id` | 티켓 분석 결과 |
| `answer_draft.ticket_id` | `qa_ticket.ticket_id` | 티켓별 답변 초안 |
| `answer_draft.analysis_id` | `ticket_analysis.analysis_id` | 분석 결과 기반 답변 초안 |
| `evidence_docs.draft_id` | `answer_draft.draft_id` | 답변 초안의 근거 문서 |
| `safety_results.draft_id` | `answer_draft.draft_id` | 답변 초안 안전성 검증 |
| `final_response.ticket_id` | `qa_ticket.ticket_id` | 티켓별 최종 응답 |
| `final_response.draft_id` | `answer_draft.draft_id` | 초안 기반 최종 응답 |
| `documents_chunks.document_id` | `documents.documents_id` | 문서와 청크 |
| `documents_embeddings.chunk_id` | `documents_chunks.chunk_id` | 청크와 임베딩 |
| `admin_event_logs.ticket_id` | `qa_ticket.ticket_id` | 티켓 처리 운영 로그 |
| `failed_queries.ticket_id` | `qa_ticket.ticket_id` | 티켓 처리 중 실패 질의 |
| `notification_logs.ticket_id` | `qa_ticket.ticket_id` | 티켓 관련 알림 |
| `insight.user_id` | `community_users.user_id` | 사용자 기반 인사이트 |
| `insight.ticket_id` | `qa_ticket.ticket_id` | 티켓 기반 인사이트 |
| `insight.account_id` | `game_accounts.account_id` | 계정 기반 인사이트 |
| `voc_feedback.user_id` | `community_users.user_id` | 사용자 VOC |
| `voc_feedback.ticket_id` | `qa_ticket.ticket_id` | 티켓 VOC |
| `voc_feedback.account_id` | `game_accounts.account_id` | 계정 VOC |

## 테이블 상세

### `admin_event_logs`

- 설명: 운영/관리 자동화 처리 과정에서 발생한 이벤트, 라우팅, 도구 호출, 오류를 기록한다.
- Primary Key: `log_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `log_id integer NOT NULL DEFAULT nextval('admin_event_logs_log_id_seq'::regclass)`
  - `ticket_id integer`
  - `session_id integer`
  - `node_name varchar(100)`
  - `event_type varchar(100)`
  - `category varchar(100)`
  - `routing_target varchar(100)`
  - `tool_name varchar(100)`
  - `status varchar(50)`
  - `error_message text`
  - `error_category varchar(100)`
  - `metadata json`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `answer_draft`

- 설명: 티켓 분석 결과를 기반으로 생성된 답변 초안을 저장한다.
- Primary Key: `draft_id`
- Foreign Key: `analysis_id` -> `ticket_analysis.analysis_id`, `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `draft_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `analysis_id integer NOT NULL`
  - `draft_text text`
  - `prompt_version varchar`
  - `created_at timestamp`

### `community_users`

- 설명: 커뮤니티 사용자 계정의 기본 식별자, 이메일, 닉네임, 상태 정보를 저장한다.
- Primary Key: `user_id`
- Columns:
  - `user_id integer NOT NULL`
  - `email varchar`
  - `nickname varchar`
  - `created_at timestamp`
  - `user_status varchar`
  - `last_login_at timestamp`

### `documents`

- 설명: RAG 검색에 사용되는 원천 문서와 출처 정보를 저장한다.
- Primary Key: `documents_id`
- Columns:
  - `documents_id varchar NOT NULL`
  - `source_type varchar`
  - `category varchar`
  - `title varchar`
  - `raw_content text`
  - `source_url varchar`
  - `published_at timestamp`
  - `updated_at timestamp`

### `documents_chunks`

- 설명: 원천 문서를 검색 가능한 청크 단위로 분할한 텍스트를 저장한다.
- Primary Key: `chunk_id`
- Unique: `document_id`, `chunk_order`
- Foreign Key: `document_id` -> `documents.documents_id`
- Indexes: `idx_documents_chunks_document_id`, `idx_documents_chunks_document_order`, `uq_documents_chunks_document_order`
- Columns:
  - `chunk_id varchar NOT NULL`
  - `document_id varchar NOT NULL`
  - `chunk_text text NOT NULL`
  - `chunk_order integer NOT NULL`
  - `token_count integer`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `documents_embeddings`

- 설명: 문서 청크별 임베딩 벡터와 임베딩 모델 정보를 저장한다.
- Primary Key: `embedding_id`
- Unique: `chunk_id`
- Foreign Key: `chunk_id` -> `documents_chunks.chunk_id`
- Indexes: `idx_documents_embeddings_chunk_id`, `idx_documents_embeddings_source_category`, `idx_documents_embeddings_vector_cosine`, `uq_documents_embeddings_chunk_id`
- Columns:
  - `embedding_id varchar NOT NULL`
  - `chunk_id varchar NOT NULL`
  - `embedding_vector vector NOT NULL`
  - `embedding_model varchar NOT NULL`
  - `source_type varchar`
  - `category varchar`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `evidence_docs`

- 설명: 답변 초안 생성 또는 검증에 사용된 근거 문서와 관련 점수를 저장한다.
- Primary Key: `evidence_id`
- Foreign Key: `draft_id` -> `answer_draft.draft_id`
- Columns:
  - `evidence_id integer NOT NULL`
  - `draft_id integer NOT NULL`
  - `source_type varchar`
  - `source_id varchar`
  - `evidence_text text`
  - `relevance_score double precision`
  - `retrieval_rank integer`

### `failed_queries`

- 설명: 티켓 처리 중 검색이나 질의 처리가 실패한 내용을 기록한다.
- Primary Key: `failed_query_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `failed_query_id integer NOT NULL DEFAULT nextval('failed_queries_failed_query_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `query text NOT NULL`
  - `category varchar(100)`
  - `reason text`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `final_response`

- 설명: 고객에게 전달할 최종 응답과 안전성 조치 결과를 저장한다.
- Primary Key: `response_id`
- Foreign Key: `draft_id` -> `answer_draft.draft_id`, `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `response_id integer NOT NULL DEFAULT nextval('final_response_response_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `draft_id integer`
  - `final_text text NOT NULL`
  - `safety_action varchar(50)`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `gacha_logs`

- 설명: 게임 계정의 가챠 배너, 획득 아이템, 희귀도, pity count, 획득 시각을 저장한다.
- Primary Key: `gacha_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`
- Columns:
  - `gacha_id integer NOT NULL`
  - `account_id integer NOT NULL`
  - `banner_name varchar`
  - `item_name varchar`
  - `item_type varchar`
  - `rarity varchar`
  - `pity_count integer`
  - `pulled_at timestamp`

### `game_accounts`

- 설명: 사용자와 연결된 게임 계정, UID, 서버, 진행도, 계정 상태를 저장한다.
- Primary Key: `account_id`
- Foreign Key: `user_id` -> `community_users.user_id`
- Columns:
  - `account_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `game_name varchar`
  - `uid varchar`
  - `server_region varchar`
  - `progression_level integer`
  - `account_status varchar`
  - `created_at timestamp`

### `insight`

- 설명: 문의 내용을 요약하고 카테고리, 감성, 위험도, 패턴 위험도를 저장한다.
- Primary Key: `insight_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`, `ticket_id` -> `qa_ticket.ticket_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `insight_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `account_id integer`
  - `content_summary text`
  - `category varchar`
  - `sentiment varchar`
  - `risk_level varchar`
  - `pattern_risk_level varchar`
  - `inquiry_created_at timestamp`

### `item_delivery_logs`

- 설명: 계정별 아이템 지급 내역, 지급 상태, 예정/완료 시각을 저장한다.
- Primary Key: `delivery_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`, `payment_id` -> `payments.payment_id`
- Columns:
  - `delivery_id integer NOT NULL`
  - `payment_id integer`
  - `account_id integer NOT NULL`
  - `source_type varchar`
  - `item_name varchar`
  - `quantity integer`
  - `delivery_status varchar`
  - `expected_at timestamp`
  - `delivered_at timestamp`

### `notification_logs`

- 설명: 티켓 관련 알림 발송 채널, 상태, 메시지, 오류 정보를 기록한다.
- Primary Key: `notification_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `notification_id integer NOT NULL DEFAULT nextval('notification_logs_notification_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `channel varchar(50)`
  - `status varchar(50)`
  - `message text`
  - `error_message text`
  - `error_category varchar(100)`
  - `sent_at timestamp DEFAULT CURRENT_TIMESTAMP`

### `payments`

- 설명: 게임 계정의 상품 결제 내역과 결제 상태, 거래 식별자를 저장한다.
- Primary Key: `payment_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`
- Columns:
  - `payment_id integer NOT NULL`
  - `account_id integer NOT NULL`
  - `product_name varchar`
  - `product_type varchar`
  - `amount numeric`
  - `currency varchar`
  - `payment_method varchar`
  - `payment_status varchar`
  - `transaction_id varchar`
  - `paid_at timestamp`

### `qa_ticket`

- 설명: 사용자 문의 티켓의 제목, 원문 질의, 접수 채널, 상태, 문의 시각을 저장한다.
- Primary Key: `ticket_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `ticket_id integer NOT NULL`
  - `account_id integer`
  - `user_id integer NOT NULL`
  - `title varchar`
  - `raw_query text`
  - `source_type varchar`
  - `status varchar`
  - `inquiry_created_at timestamp`
  - `session_id integer`

### `refunds`

- 설명: 결제 건별 환불 상태, 사유, 요청/처리 시각을 저장한다.
- Primary Key: `refund_id`
- Foreign Key: `payment_id` -> `payments.payment_id`
- Columns:
  - `refund_id integer NOT NULL`
  - `payment_id integer NOT NULL`
  - `refund_status varchar`
  - `refund_reason text`
  - `requested_at timestamp`
  - `processed_at timestamp`

### `safety_results`

- 설명: 답변 초안에 대한 환각, 독성, 정책 위반, 사실성 점수와 최종 안전 조치를 저장한다.
- Primary Key: `safety_id`
- Foreign Key: `draft_id` -> `answer_draft.draft_id`
- Columns:
  - `safety_id integer NOT NULL`
  - `draft_id integer NOT NULL`
  - `hallucination_score double precision`
  - `toxicity_score double precision`
  - `policy_violation_score double precision`
  - `factuality_score double precision`
  - `checked_at timestamp`
  - `safety_action varchar(100)`
  - `safety_reason varchar(255)`
  - `retry_count integer DEFAULT 0`

### `ticket_analysis`

- 설명: QA 티켓의 카테고리, 응답자 유형, 보강 질의, 위험도, 감성, 라우팅 대상, 요약을 저장한다.
- Primary Key: `analysis_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `analysis_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `category varchar`
  - `responder_type varchar`
  - `enriched_query text`
  - `risk_level varchar`
  - `sentiment varchar`
  - `routing_target varchar`
  - `summary text`
  - `analyzed_at timestamp`

### `voc_feedback`

- 설명: 사용자 VOC 유형, 감성, 원문, 토픽 키워드를 저장한다.
- Primary Key: `voc_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`, `ticket_id` -> `qa_ticket.ticket_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `voc_id integer NOT NULL DEFAULT nextval('voc_feedback_voc_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `account_id integer`
  - `voc_type varchar(100)`
  - `sentiment varchar(50)`
  - `raw_content text NOT NULL`
  - `topic_keywords json`
  - `created_at timestamp DEFAULT CURRENT_TIMESTAMP`
