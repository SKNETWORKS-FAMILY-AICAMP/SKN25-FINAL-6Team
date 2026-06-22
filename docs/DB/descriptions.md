# DB Descriptions

Generated from the live PostgreSQL database on 2026-06-18.

## Basic Info

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit` |
| Host | `100.97.235.15` |
| Server Address | `100.97.235.15/32` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public Tables | 19 |
| Public Columns | 151 |
| `_ex` Tables | 0 |

## Table Summary

Row counts are exact `COUNT(*)` results at verification time.

| Table | Exact Rows | Columns | Primary Key | PK Default | Purpose |
| --- | ---: | ---: | --- | --- | --- |
| `admin_users` | 10 | 9 | `admin_id` | `nextval('admin_users_admin_id_seq'::regclass)` | Administrator/operator login accounts and auth metadata |
| `answer_draft` | 30 | 6 | `draft_id` | `IDENTITY` | Generated answer drafts for tickets |
| `community_users` | 1,500 | 8 | `user_id` | none | Community user profile data |
| `documents` | 1,068 | 8 | `documents_id` | none | Source documents used by the current RAG corpus |
| `documents_chunks` | 5,068 | 6 | `chunk_id` | none | Searchable chunks for the current RAG corpus |
| `documents_embeddings` | 5,068 | 7 | `embedding_id` | none | Vector embeddings for document chunks |
| `evidence_docs` | 106 | 7 | `evidence_id` | `IDENTITY` | Retrieved evidence saved for answer drafts |
| `failed_queries` | 3 | 6 | `failed_query_id` | `IDENTITY` | Failed ticket/query processing logs |
| `final_response` | 13 | 6 | `response_id` | `IDENTITY` | Final customer-facing responses |
| `gacha_logs` | 25,000 | 8 | `gacha_id` | none | Gacha pull history per game account |
| `game_accounts` | 1,500 | 8 | `account_id` | none | Game account data linked to community users |
| `insight` | 0 | 10 | `insight_id` | `nextval('insight_insight_id_seq'::regclass)` | Ticket/user/account-level insight analysis data |
| `item_delivery_logs` | 10,000 | 9 | `delivery_id` | none | Paid or reward item delivery history |
| `notification_logs` | 0 | 7 | `notification_id` | `nextval('notification_logs_notification_id_seq'::regclass)` | Notification send results and errors |
| `payments` | 5,000 | 10 | `payment_id` | none | Payment transaction history |
| `qa_ticket` | 9,257 | 10 | `ticket_id` | `IDENTITY` | Customer inquiry/QA tickets |
| `refunds` | 300 | 6 | `refund_id` | none | Refund request and processing history |
| `safety_results` | 26 | 10 | `safety_id` | `IDENTITY` | Safety and grounding check results for drafts |
| `ticket_analysis` | 0 | 10 | `analysis_id` | `IDENTITY` | Ticket classification, risk, sentiment, and routing analysis |

## Data Type Summary

| Data Type | PostgreSQL UDT | Column Count |
| --- | --- | ---: |
| `USER-DEFINED` | `vector` | 1 |
| `character varying` | `varchar` | 58 |
| `double precision` | `float8` | 5 |
| `integer` | `int4` | 44 |
| `numeric` | `numeric` | 1 |
| `text` | `text` | 17 |
| `timestamp without time zone` | `timestamp` | 25 |

## Current Schema Notes

- The live `public` schema currently has 19 tables and no `_ex` mirror/template tables.
- The RAG source table is `documents`, and retrieval artifacts live in `documents_chunks` and `documents_embeddings`.
- Older repo documents that describe `sj_documents`, `test_documents_chunks`, `test_documents_embeddings_large`, `test_documents_embeddings_small`, or `_ex` tables are historical references, not live-schema facts.
- `apps/weekly_report/db/top_requests.py` currently attempts to read `voc_feedback.topic_keywords`, but `voc_feedback` is not present in the live schema captured in this document. The implementation falls back to empty keywords when that lookup fails.
- `qa_ticket`, `answer_draft`, `notification_logs`, and `ticket_analysis` have ordinal gaps in `information_schema.columns`, which indicates earlier schema revisions with dropped columns; the current column counts above are authoritative.

## Workflow Read/Write Map

| Phase | Live Tables |
| --- | --- |
| Admin auth | `admin_users` |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `payments`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse/VOC context | `insight` |
| RAG source | `documents` |
| RAG retrieval | `documents_chunks`, `documents_embeddings` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries` |

## Foreign Key Summary

| Column | References | On Update | On Delete |
| --- | --- | --- | --- |
| `answer_draft.analysis_id` | `ticket_analysis.analysis_id` | NO ACTION | CASCADE |
| `answer_draft.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | CASCADE |
| `evidence_docs.draft_id` | `answer_draft.draft_id` | NO ACTION | CASCADE |
| `failed_queries.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `final_response.draft_id` | `answer_draft.draft_id` | NO ACTION | NO ACTION |
| `final_response.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | CASCADE |
| `gacha_logs.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `game_accounts.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `insight.account_id` | `game_accounts.account_id` | NO ACTION | SET NULL |
| `insight.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `insight.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `item_delivery_logs.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `item_delivery_logs.payment_id` | `payments.payment_id` | NO ACTION | SET NULL |
| `notification_logs.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `payments.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `qa_ticket.account_id` | `game_accounts.account_id` | NO ACTION | SET NULL |
| `qa_ticket.assignee_admin_id` | `admin_users.admin_id` | NO ACTION | SET NULL |
| `qa_ticket.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `refunds.payment_id` | `payments.payment_id` | NO ACTION | CASCADE |
| `safety_results.draft_id` | `answer_draft.draft_id` | NO ACTION | CASCADE |
| `documents_chunks.document_id` | `documents.documents_id` | NO ACTION | NO ACTION |
| `documents_embeddings.chunk_id` | `documents_chunks.chunk_id` | NO ACTION | CASCADE |
| `ticket_analysis.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |

## Index Summary

| Table | Index | Definition |
| --- | --- | --- |
| `admin_users` | `admin_users_pkey` | `UNIQUE INDEX admin_users_pkey ON public.admin_users USING btree (admin_id)` |
| `admin_users` | `uq_admin_users_login_id` | `UNIQUE INDEX uq_admin_users_login_id ON public.admin_users USING btree (login_id)` |
| `answer_draft` | `answer_draft_pkey` | `UNIQUE INDEX answer_draft_pkey ON public.answer_draft USING btree (draft_id)` |
| `answer_draft` | `idx_answer_draft_ticket_id` | `INDEX idx_answer_draft_ticket_id ON public.answer_draft USING btree (ticket_id)` |
| `community_users` | `community_users_pkey` | `UNIQUE INDEX community_users_pkey ON public.community_users USING btree (user_id)` |
| `documents` | `sj_documents_pkey` | `UNIQUE INDEX sj_documents_pkey ON public.documents USING btree (documents_id)` |
| `documents_chunks` | `idx_test_documents_chunks_document_id` | `INDEX idx_test_documents_chunks_document_id ON public.documents_chunks USING btree (document_id)` |
| `documents_chunks` | `idx_test_documents_chunks_document_order` | `INDEX idx_test_documents_chunks_document_order ON public.documents_chunks USING btree (document_id, chunk_order)` |
| `documents_chunks` | `test_documents_chunks_pkey` | `UNIQUE INDEX test_documents_chunks_pkey ON public.documents_chunks USING btree (chunk_id)` |
| `documents_chunks` | `uq_test_documents_chunks_document_order` | `UNIQUE INDEX uq_test_documents_chunks_document_order ON public.documents_chunks USING btree (document_id, chunk_order)` |
| `documents_embeddings` | `idx_test_documents_embeddings_small_chunk_id` | `INDEX idx_test_documents_embeddings_small_chunk_id ON public.documents_embeddings USING btree (chunk_id)` |
| `documents_embeddings` | `idx_test_documents_embeddings_small_source_category` | `INDEX idx_test_documents_embeddings_small_source_category ON public.documents_embeddings USING btree (source_type, category)` |
| `documents_embeddings` | `idx_test_documents_embeddings_small_vector_cosine` | `INDEX idx_test_documents_embeddings_small_vector_cosine ON public.documents_embeddings USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists='100')` |
| `documents_embeddings` | `test_documents_embeddings_small_pkey` | `UNIQUE INDEX test_documents_embeddings_small_pkey ON public.documents_embeddings USING btree (embedding_id)` |
| `documents_embeddings` | `uq_test_documents_embeddings_small_chunk_id` | `UNIQUE INDEX uq_test_documents_embeddings_small_chunk_id ON public.documents_embeddings USING btree (chunk_id)` |
| `evidence_docs` | `evidence_docs_pkey` | `UNIQUE INDEX evidence_docs_pkey ON public.evidence_docs USING btree (evidence_id)` |
| `failed_queries` | `failed_queries_pkey` | `UNIQUE INDEX failed_queries_pkey ON public.failed_queries USING btree (failed_query_id)` |
| `final_response` | `final_response_pkey` | `UNIQUE INDEX final_response_pkey ON public.final_response USING btree (response_id)` |
| `gacha_logs` | `gacha_logs_pkey` | `UNIQUE INDEX gacha_logs_pkey ON public.gacha_logs USING btree (gacha_id)` |
| `game_accounts` | `game_accounts_pkey` | `UNIQUE INDEX game_accounts_pkey ON public.game_accounts USING btree (account_id)` |
| `insight` | `insight_pkey` | `UNIQUE INDEX insight_pkey ON public.insight USING btree (insight_id)` |
| `item_delivery_logs` | `item_delivery_logs_pkey` | `UNIQUE INDEX item_delivery_logs_pkey ON public.item_delivery_logs USING btree (delivery_id)` |
| `notification_logs` | `notification_logs_pkey` | `UNIQUE INDEX notification_logs_pkey ON public.notification_logs USING btree (notification_id)` |
| `payments` | `payments_pkey` | `UNIQUE INDEX payments_pkey ON public.payments USING btree (payment_id)` |
| `qa_ticket` | `idx_qa_ticket_assignee_admin_id` | `INDEX idx_qa_ticket_assignee_admin_id ON public.qa_ticket USING btree (assignee_admin_id)` |
| `qa_ticket` | `idx_qa_ticket_inquiry_created_at` | `INDEX idx_qa_ticket_inquiry_created_at ON public.qa_ticket USING btree (inquiry_created_at)` |
| `qa_ticket` | `qa_ticket_pkey` | `UNIQUE INDEX qa_ticket_pkey ON public.qa_ticket USING btree (ticket_id)` |
| `refunds` | `refunds_pkey` | `UNIQUE INDEX refunds_pkey ON public.refunds USING btree (refund_id)` |
| `safety_results` | `idx_safety_results_draft_id` | `INDEX idx_safety_results_draft_id ON public.safety_results USING btree (draft_id)` |
| `safety_results` | `safety_results_pkey` | `UNIQUE INDEX safety_results_pkey ON public.safety_results USING btree (safety_id)` |
| `ticket_analysis` | `idx_ticket_analysis_analyzed_at` | `INDEX idx_ticket_analysis_analyzed_at ON public.ticket_analysis USING btree (analyzed_at)` |
| `ticket_analysis` | `ticket_analysis_pkey` | `UNIQUE INDEX ticket_analysis_pkey ON public.ticket_analysis USING btree (analysis_id)` |

## Table Details

### `admin_users`

- Exact Rows: 10
- Purpose: Administrator/operator login accounts and auth metadata
- Primary Key: `admin_id`
- PK Default: `nextval('admin_users_admin_id_seq'::regclass)`
- Foreign Keys: none

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `admin_id` | `int4` | NO | `nextval('admin_users_admin_id_seq'::regclass)` | PK, UNIQUE |
| 2 | `login_id` | `varchar(100)` | NO | `` | UNIQUE |
| 3 | `password_hash` | `text` | NO | `` |  |
| 4 | `display_name` | `varchar(100)` | NO | `` |  |
| 5 | `role` | `varchar(30)` | NO | `` |  |
| 6 | `status` | `varchar(30)` | NO | `'active'::character varying` |  |
| 7 | `last_login_at` | `timestamp` | YES | `` |  |
| 8 | `password_updated_at` | `timestamp` | NO | `CURRENT_TIMESTAMP` |  |
| 9 | `created_at` | `timestamp` | NO | `CURRENT_TIMESTAMP` |  |

Indexes:

- `admin_users_pkey`: `UNIQUE INDEX admin_users_pkey ON public.admin_users USING btree (admin_id)`
- `uq_admin_users_login_id`: `UNIQUE INDEX uq_admin_users_login_id ON public.admin_users USING btree (login_id)`

### `answer_draft`

- Exact Rows: 30
- Purpose: Generated answer drafts for tickets
- Primary Key: `draft_id`
- PK Default: `IDENTITY`
- Foreign Keys: `analysis_id` -> `ticket_analysis.analysis_id` (CASCADE), `ticket_id` -> `qa_ticket.ticket_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `draft_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 3 | `analysis_id` | `int4` | YES | `` | FK -> `ticket_analysis.analysis_id` |
| 4 | `draft_text` | `text` | YES | `` |  |
| 6 | `created_at` | `timestamp` | YES | `` |  |
| 7 | `prompt_version` | `varchar(100)` | YES | `` |  |

Indexes:

- `answer_draft_pkey`: `UNIQUE INDEX answer_draft_pkey ON public.answer_draft USING btree (draft_id)`
- `idx_answer_draft_ticket_id`: `INDEX idx_answer_draft_ticket_id ON public.answer_draft USING btree (ticket_id)`

### `community_users`

- Exact Rows: 1,500
- Purpose: Community user profile data
- Primary Key: `user_id`
- PK Default: none
- Foreign Keys: none

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `user_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `email` | `varchar` | YES | `` |  |
| 3 | `nickname` | `varchar` | YES | `` |  |
| 4 | `created_at` | `timestamp` | YES | `` |  |
| 5 | `user_status` | `varchar` | YES | `` |  |
| 6 | `last_login_at` | `timestamp` | YES | `` |  |
| 7 | `password_hash` | `text` | YES | `` |  |
| 8 | `password_updated_at` | `timestamp` | YES | `` |  |

Indexes:

- `community_users_pkey`: `UNIQUE INDEX community_users_pkey ON public.community_users USING btree (user_id)`

### `evidence_docs`

- Exact Rows: 106
- Purpose: Retrieved evidence saved for answer drafts
- Primary Key: `evidence_id`
- PK Default: `IDENTITY`
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `evidence_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `draft_id` | `int4` | NO | `` | FK -> `answer_draft.draft_id` |
| 3 | `source_type` | `varchar` | YES | `` |  |
| 4 | `source_id` | `varchar` | YES | `` |  |
| 5 | `evidence_text` | `text` | YES | `` |  |
| 6 | `relevance_score` | `float8` | YES | `` |  |
| 7 | `retrieval_rank` | `int4` | YES | `` |  |

Indexes:

- `evidence_docs_pkey`: `UNIQUE INDEX evidence_docs_pkey ON public.evidence_docs USING btree (evidence_id)`

### `failed_queries`

- Exact Rows: 3
- Purpose: Failed ticket/query processing logs
- Primary Key: `failed_query_id`
- PK Default: `IDENTITY`
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `failed_query_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 3 | `query` | `text` | NO | `` |  |
| 4 | `category` | `varchar(100)` | YES | `` |  |
| 5 | `reason` | `text` | YES | `` |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

Indexes:

- `failed_queries_pkey`: `UNIQUE INDEX failed_queries_pkey ON public.failed_queries USING btree (failed_query_id)`

### `final_response`

- Exact Rows: 13
- Purpose: Final customer-facing responses
- Primary Key: `response_id`
- PK Default: `IDENTITY`
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (NO ACTION), `ticket_id` -> `qa_ticket.ticket_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `response_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 3 | `draft_id` | `int4` | YES | `` | FK -> `answer_draft.draft_id` |
| 4 | `final_text` | `text` | NO | `` |  |
| 5 | `safety_action` | `varchar(50)` | YES | `` |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

Indexes:

- `final_response_pkey`: `UNIQUE INDEX final_response_pkey ON public.final_response USING btree (response_id)`

### `gacha_logs`

- Exact Rows: 25,000
- Purpose: Gacha pull history per game account
- Primary Key: `gacha_id`
- PK Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `gacha_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `account_id` | `int4` | NO | `` | FK -> `game_accounts.account_id` |
| 3 | `banner_name` | `varchar` | YES | `` |  |
| 4 | `item_name` | `varchar` | YES | `` |  |
| 5 | `item_type` | `varchar` | YES | `` |  |
| 6 | `rarity` | `varchar` | YES | `` |  |
| 7 | `pity_count` | `int4` | YES | `` |  |
| 8 | `pulled_at` | `timestamp` | YES | `` |  |

Indexes:

- `gacha_logs_pkey`: `UNIQUE INDEX gacha_logs_pkey ON public.gacha_logs USING btree (gacha_id)`

### `game_accounts`

- Exact Rows: 1,500
- Purpose: Game account data linked to community users
- Primary Key: `account_id`
- PK Default: none
- Foreign Keys: `user_id` -> `community_users.user_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `account_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `user_id` | `int4` | NO | `` | FK -> `community_users.user_id` |
| 3 | `game_name` | `varchar` | YES | `` |  |
| 4 | `uid` | `varchar` | YES | `` |  |
| 5 | `server_region` | `varchar` | YES | `` |  |
| 6 | `progression_level` | `int4` | YES | `` |  |
| 7 | `account_status` | `varchar` | YES | `` |  |
| 8 | `created_at` | `timestamp` | YES | `` |  |

Indexes:

- `game_accounts_pkey`: `UNIQUE INDEX game_accounts_pkey ON public.game_accounts USING btree (account_id)`

### `insight`

- Exact Rows: 0
- Purpose: Ticket/user/account-level insight analysis data
- Primary Key: `insight_id`
- PK Default: `nextval('insight_insight_id_seq'::regclass)`
- Foreign Keys: `account_id` -> `game_accounts.account_id` (SET NULL), `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION), `user_id` -> `community_users.user_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `insight_id` | `int4` | NO | `nextval('insight_insight_id_seq'::regclass)` | PK, UNIQUE |
| 2 | `user_id` | `int4` | NO | `` | FK -> `community_users.user_id` |
| 3 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 4 | `account_id` | `int4` | YES | `` | FK -> `game_accounts.account_id` |
| 5 | `content_summary` | `text` | YES | `` |  |
| 6 | `category` | `varchar` | YES | `` |  |
| 7 | `sentiment` | `varchar` | YES | `` |  |
| 8 | `risk_level` | `varchar` | YES | `` |  |
| 9 | `pattern_risk_level` | `varchar` | YES | `` |  |
| 10 | `inquiry_created_at` | `timestamp` | YES | `` |  |

Indexes:

- `insight_pkey`: `UNIQUE INDEX insight_pkey ON public.insight USING btree (insight_id)`

### `item_delivery_logs`

- Exact Rows: 10,000
- Purpose: Paid or reward item delivery history
- Primary Key: `delivery_id`
- PK Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE), `payment_id` -> `payments.payment_id` (SET NULL)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `delivery_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `payment_id` | `int4` | YES | `` | FK -> `payments.payment_id` |
| 3 | `account_id` | `int4` | NO | `` | FK -> `game_accounts.account_id` |
| 4 | `source_type` | `varchar` | YES | `` |  |
| 5 | `item_name` | `varchar` | YES | `` |  |
| 6 | `quantity` | `int4` | YES | `` |  |
| 7 | `delivery_status` | `varchar` | YES | `` |  |
| 8 | `expected_at` | `timestamp` | YES | `` |  |
| 9 | `delivered_at` | `timestamp` | YES | `` |  |

Indexes:

- `item_delivery_logs_pkey`: `UNIQUE INDEX item_delivery_logs_pkey ON public.item_delivery_logs USING btree (delivery_id)`

### `notification_logs`

- Exact Rows: 0
- Purpose: Notification send results and errors
- Primary Key: `notification_id`
- PK Default: `nextval('notification_logs_notification_id_seq'::regclass)`
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `notification_id` | `int4` | NO | `nextval('notification_logs_notification_id_seq'::regclass)` | PK, UNIQUE |
| 2 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 3 | `channel` | `varchar(50)` | YES | `` |  |
| 4 | `status` | `varchar(50)` | YES | `` |  |
| 5 | `message` | `text` | YES | `` |  |
| 6 | `error_message` | `text` | YES | `` |  |
| 8 | `sent_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

Indexes:

- `notification_logs_pkey`: `UNIQUE INDEX notification_logs_pkey ON public.notification_logs USING btree (notification_id)`

### `payments`

- Exact Rows: 5,000
- Purpose: Payment transaction history
- Primary Key: `payment_id`
- PK Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `payment_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `account_id` | `int4` | NO | `` | FK -> `game_accounts.account_id` |
| 3 | `product_name` | `varchar` | YES | `` |  |
| 4 | `product_type` | `varchar` | YES | `` |  |
| 5 | `amount` | `numeric` | YES | `` |  |
| 6 | `currency` | `varchar` | YES | `` |  |
| 7 | `payment_method` | `varchar` | YES | `` |  |
| 8 | `payment_status` | `varchar` | YES | `` |  |
| 9 | `transaction_id` | `varchar` | YES | `` |  |
| 10 | `paid_at` | `timestamp` | YES | `` |  |

Indexes:

- `payments_pkey`: `UNIQUE INDEX payments_pkey ON public.payments USING btree (payment_id)`

### `qa_ticket`

- Exact Rows: 9,257
- Purpose: Customer inquiry/QA tickets
- Primary Key: `ticket_id`
- PK Default: `IDENTITY`
- Foreign Keys: `account_id` -> `game_accounts.account_id` (SET NULL), `assignee_admin_id` -> `admin_users.admin_id` (SET NULL), `user_id` -> `community_users.user_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `ticket_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `account_id` | `int4` | NO | `` | FK -> `game_accounts.account_id` |
| 3 | `user_id` | `int4` | NO | `` | FK -> `community_users.user_id` |
| 4 | `title` | `varchar` | YES | `` |  |
| 5 | `raw_query` | `text` | YES | `` |  |
| 6 | `source_type` | `varchar` | YES | `` |  |
| 7 | `status` | `varchar` | YES | `` |  |
| 8 | `inquiry_created_at` | `timestamp` | YES | `` |  |
| 9 | `session_id` | `text` | YES | `` |  |
| 11 | `assignee_admin_id` | `int4` | YES | `` | FK -> `admin_users.admin_id` |

Indexes:

- `idx_qa_ticket_assignee_admin_id`: `INDEX idx_qa_ticket_assignee_admin_id ON public.qa_ticket USING btree (assignee_admin_id)`
- `idx_qa_ticket_inquiry_created_at`: `INDEX idx_qa_ticket_inquiry_created_at ON public.qa_ticket USING btree (inquiry_created_at)`
- `qa_ticket_pkey`: `UNIQUE INDEX qa_ticket_pkey ON public.qa_ticket USING btree (ticket_id)`

### `refunds`

- Exact Rows: 300
- Purpose: Refund request and processing history
- Primary Key: `refund_id`
- PK Default: none
- Foreign Keys: `payment_id` -> `payments.payment_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `refund_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `payment_id` | `int4` | NO | `` | FK -> `payments.payment_id` |
| 3 | `refund_status` | `varchar` | YES | `` |  |
| 4 | `refund_reason` | `text` | YES | `` |  |
| 5 | `requested_at` | `timestamp` | YES | `` |  |
| 6 | `processed_at` | `timestamp` | YES | `` |  |

Indexes:

- `refunds_pkey`: `UNIQUE INDEX refunds_pkey ON public.refunds USING btree (refund_id)`

### `safety_results`

- Exact Rows: 26
- Purpose: Safety and grounding check results for drafts
- Primary Key: `safety_id`
- PK Default: `IDENTITY`
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `safety_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `draft_id` | `int4` | NO | `` | FK -> `answer_draft.draft_id` |
| 3 | `hallucination_score` | `float8` | YES | `` |  |
| 4 | `toxicity_score` | `float8` | YES | `` |  |
| 5 | `policy_violation_score` | `float8` | YES | `` |  |
| 6 | `factuality_score` | `float8` | YES | `` |  |
| 7 | `checked_at` | `timestamp` | YES | `` |  |
| 8 | `safety_action` | `varchar(100)` | YES | `` |  |
| 9 | `safety_reason` | `varchar(255)` | YES | `` |  |
| 10 | `retry_count` | `int4` | YES | `0` |  |

Indexes:

- `idx_safety_results_draft_id`: `INDEX idx_safety_results_draft_id ON public.safety_results USING btree (draft_id)`
- `safety_results_pkey`: `UNIQUE INDEX safety_results_pkey ON public.safety_results USING btree (safety_id)`

### `documents`

- Exact Rows: 1,068
- Purpose: Source documents used by the current RAG corpus
- Primary Key: `documents_id`
- PK Default: none
- Foreign Keys: none

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `documents_id` | `varchar` | NO | `` | PK, UNIQUE |
| 2 | `source_type` | `varchar` | YES | `` |  |
| 3 | `category` | `varchar` | YES | `` |  |
| 4 | `title` | `varchar` | YES | `` |  |
| 5 | `raw_content` | `text` | YES | `` |  |
| 6 | `source_url` | `varchar` | YES | `` |  |
| 7 | `published_at` | `timestamp` | YES | `` |  |
| 8 | `updated_at` | `timestamp` | YES | `` |  |

Indexes:

- `sj_documents_pkey`: `UNIQUE INDEX sj_documents_pkey ON public.documents USING btree (documents_id)`

### `documents_chunks`

- Exact Rows: 5,068
- Purpose: Searchable chunks for the current RAG corpus
- Primary Key: `chunk_id`
- PK Default: none
- Foreign Keys: `document_id` -> `documents.documents_id` (NO ACTION)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `chunk_id` | `varchar` | NO | `` | PK, UNIQUE |
| 2 | `document_id` | `varchar` | NO | `` | FK -> `documents.documents_id` |
| 3 | `chunk_text` | `text` | NO | `` |  |
| 4 | `chunk_order` | `int4` | NO | `` |  |
| 5 | `token_count` | `int4` | YES | `` |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

Indexes:

- `idx_test_documents_chunks_document_id`: `INDEX idx_test_documents_chunks_document_id ON public.documents_chunks USING btree (document_id)`
- `idx_test_documents_chunks_document_order`: `INDEX idx_test_documents_chunks_document_order ON public.documents_chunks USING btree (document_id, chunk_order)`
- `test_documents_chunks_pkey`: `UNIQUE INDEX test_documents_chunks_pkey ON public.documents_chunks USING btree (chunk_id)`
- `uq_test_documents_chunks_document_order`: `UNIQUE INDEX uq_test_documents_chunks_document_order ON public.documents_chunks USING btree (document_id, chunk_order)`

### `documents_embeddings`

- Exact Rows: 5,068
- Purpose: Vector embeddings for document chunks
- Primary Key: `embedding_id`
- PK Default: none
- Foreign Keys: `chunk_id` -> `documents_chunks.chunk_id` (CASCADE)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `embedding_id` | `varchar` | NO | `` | PK, UNIQUE |
| 2 | `chunk_id` | `varchar` | NO | `` | UNIQUE, FK -> `documents_chunks.chunk_id` |
| 3 | `embedding_vector` | `vector` | YES | `` |  |
| 4 | `embedding_model` | `varchar` | YES | `` |  |
| 5 | `source_type` | `varchar` | YES | `` |  |
| 6 | `category` | `varchar` | YES | `` |  |
| 7 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

Indexes:

- `idx_test_documents_embeddings_small_chunk_id`: `INDEX idx_test_documents_embeddings_small_chunk_id ON public.documents_embeddings USING btree (chunk_id)`
- `idx_test_documents_embeddings_small_source_category`: `INDEX idx_test_documents_embeddings_small_source_category ON public.documents_embeddings USING btree (source_type, category)`
- `idx_test_documents_embeddings_small_vector_cosine`: `INDEX idx_test_documents_embeddings_small_vector_cosine ON public.documents_embeddings USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists='100')`
- `test_documents_embeddings_small_pkey`: `UNIQUE INDEX test_documents_embeddings_small_pkey ON public.documents_embeddings USING btree (embedding_id)`
- `uq_test_documents_embeddings_small_chunk_id`: `UNIQUE INDEX uq_test_documents_embeddings_small_chunk_id ON public.documents_embeddings USING btree (chunk_id)`

### `ticket_analysis`

- Exact Rows: 0
- Purpose: Ticket classification, risk, sentiment, and routing analysis
- Primary Key: `analysis_id`
- PK Default: `IDENTITY`
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)

| # | Column | Type | Nullable | Default | Notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `analysis_id` | `int4` | NO | `` | PK, UNIQUE |
| 2 | `ticket_id` | `int4` | NO | `` | FK -> `qa_ticket.ticket_id` |
| 3 | `category` | `varchar` | YES | `` |  |
| 4 | `responder_type` | `varchar` | YES | `` |  |
| 5 | `enriched_query` | `text` | YES | `` |  |
| 6 | `risk_level` | `varchar` | YES | `` |  |
| 7 | `sentiment` | `varchar` | YES | `` |  |
| 9 | `routing_target` | `varchar` | YES | `` |  |
| 10 | `summary` | `text` | YES | `` |  |
| 11 | `analyzed_at` | `timestamp` | YES | `` |  |

Indexes:

- `idx_ticket_analysis_analyzed_at`: `INDEX idx_ticket_analysis_analyzed_at ON public.ticket_analysis USING btree (analyzed_at)`
- `ticket_analysis_pkey`: `UNIQUE INDEX ticket_analysis_pkey ON public.ticket_analysis USING btree (analysis_id)`

