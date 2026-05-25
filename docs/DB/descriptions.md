# DB Descriptions

Generated from the live PostgreSQL database on 2026-05-26.

## Basic Info

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)` |
| Host | `100.97.235.15` |
| Server Address | `100.97.235.15/32` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public Tables | 40 |
| Public Columns | 330 |

## Table Summary

Row counts are PostgreSQL `pg_stat_user_tables.n_live_tup` estimates at verification time. The current public schema contains 20 main tables and 20 `_ex` template/mirror tables.

| Table | Estimated Rows | Columns | Primary Key | PK Default | Purpose |
| --- | ---: | ---: | --- | --- | --- |
| `admin_event_logs` | 0 | 13 | `log_id` | `nextval('admin_event_logs_log_id_seq'::regclass)` | Operation/admin workflow event and error logs |
| `admin_event_logs_ex` | 3 | 13 | none | none | Template/example copy of `admin_event_logs` |
| `answer_draft` | 0 | 6 | `draft_id` | none | Generated answer drafts for tickets |
| `answer_draft_ex` | 329 | 6 | none | none | Template/example copy of `answer_draft` |
| `community_users` | 630 | 8 | `user_id` | none | Reduced community user profile data |
| `community_users_ex` | 6,288 | 8 | none | none | Template/source-scale copy of `community_users` |
| `documents` | 1,201 | 8 | `documents_id` | none | Source documents for policy, notice, guide, incident, and RAG retrieval |
| `documents_chunks` | 0 | 6 | `chunk_id` | none | Searchable chunks split from source documents |
| `documents_chunks_ex` | 3,864 | 6 | none | none | Template/example copy of `documents_chunks` |
| `documents_embeddings` | 0 | 7 | `embedding_id` | none | Vector embeddings for document chunks |
| `documents_embeddings_ex` | 3,864 | 7 | none | none | Template/example copy of `documents_embeddings` |
| `documents_ex` | 1,201 | 8 | none | none | Template/example copy of `documents` |
| `evidence_docs` | 0 | 7 | `evidence_id` | none | Retrieved evidence saved for answer drafts |
| `evidence_docs_ex` | 837 | 7 | none | none | Template/example copy of `evidence_docs` |
| `failed_queries` | 0 | 6 | `failed_query_id` | none | Failed ticket/query processing logs |
| `failed_queries_ex` | 11 | 6 | none | none | Template/example copy of `failed_queries` |
| `final_response` | 0 | 6 | `response_id` | none | Final customer-facing responses |
| `final_response_ex` | 311 | 6 | none | none | Template/example copy of `final_response` |
| `gacha_logs` | 180 | 8 | `gacha_id` | none | Reduced gacha pull history per game account |
| `gacha_logs_ex` | 5 | 8 | none | none | Template/example copy of `gacha_logs` |
| `game_accounts` | 630 | 8 | `account_id` | none | Reduced game account data linked to community users |
| `game_accounts_ex` | 6,288 | 8 | none | none | Template/source-scale copy of `game_accounts` |
| `insight` | 0 | 10 | `insight_id` | none | Ticket/user/account-level insight analysis data |
| `insight_ex` | 5 | 10 | none | none | Template/example copy of `insight` |
| `item_delivery_logs` | 140 | 9 | `delivery_id` | none | Reduced paid or reward item delivery history |
| `item_delivery_logs_ex` | 5 | 9 | none | none | Template/example copy of `item_delivery_logs` |
| `notification_logs` | 0 | 8 | `notification_id` | `nextval('notification_logs_notification_id_seq'::regclass)` | Notification send results and errors |
| `notification_logs_ex` | 2 | 8 | none | none | Template/example copy of `notification_logs` |
| `payments` | 320 | 10 | `payment_id` | none | Reduced payment transaction history |
| `payments_ex` | 11 | 10 | none | none | Template/example copy of `payments` |
| `qa_ticket` | 950 | 10 | `ticket_id` | none | Reduced customer inquiry/QA tickets |
| `qa_ticket_ex` | 9,349 | 10 | none | none | Template/source-scale copy of `qa_ticket` |
| `refunds` | 55 | 6 | `refund_id` | none | Reduced refund request and processing history |
| `refunds_ex` | 5 | 6 | none | none | Template/example copy of `refunds` |
| `safety_results` | 0 | 10 | `safety_id` | none | Safety and grounding check results for drafts |
| `safety_results_ex` | 287 | 10 | none | none | Template/example copy of `safety_results` |
| `ticket_analysis` | 0 | 10 | `analysis_id` | none | Ticket classification, risk, sentiment, and routing analysis |
| `ticket_analysis_ex` | 351 | 10 | none | none | Template/example copy of `ticket_analysis` |
| `voc_feedback` | 0 | 9 | `voc_id` | none | VOC feedback and topic keyword records |
| `voc_feedback_ex` | 43 | 9 | none | none | Template/example copy of `voc_feedback` |

## Data Type Summary

| Data Type | PostgreSQL UDT | Column Count |
| --- | --- | ---: |
| `USER-DEFINED` | `vector` | 2 |
| `character varying` | `varchar` | 130 |
| `double precision` | `float8` | 10 |
| `integer` | `int4` | 100 |
| `json` | `json` | 4 |
| `numeric` | `numeric` | 2 |
| `text` | `text` | 34 |
| `timestamp without time zone` | `timestamp` | 48 |

## Data Load Sources

| Source | Target Tables | Notes |
| --- | --- | --- |
| `data/processed/community_users.csv` | `community_users` | 9,221 source rows; upserted by `user_id`, resulting in 6,288 distinct users in the table. |
| `data/processed/qa_ticket.csv` | `qa_ticket` | `source_type` appears twice in the CSV header and `notebooks/insert_processed_data.ipynb` keeps the first occurrence. |
| `notebooks/insert_processed_data.ipynb` | `community_users`, `game_accounts`, `qa_ticket` | Derives game account rows from distinct non-null `qa_ticket.account_id` to `user_id` mappings before loading tickets. |
| `notebooks/generate_operation_workflow_sample_data.ipynb` | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight`, `voc_feedback` | Adds operation workflow sample context rows used by the LangGraph workflow. |

## Reduced Dataset Reference

The reduced dataset workflow documented in `docs/data_generation/` reuses this live schema as its baseline.

- `docs/data_generation/plan.md` defines the reduced-table scope and target counts for `community_users`, `game_accounts`, `qa_ticket`, `payments`, `refunds`, `item_delivery_logs`, and `gacha_logs`.
- `docs/data_generation/repopulate_reduced_dataset.py` truncates and repopulates those seven tables using live `_ex` templates plus target-count logic.
- `docs/data_generation/paper_description.md` records the methodological rationale: preserve real `qa_ticket` structure where possible, supplement only limited hard cases, and keep synthetic rows explainable through game-domain operation logs.

## `_ex` Mirror Table Note

The `_ex` tables are template or source-scale mirrors paired with the 20 main tables.

- Main tables reflect the current reduced dataset and current workflow output state.
- `_ex` tables preserve template/example rows or source-scale reference data.
- Detailed column descriptions below focus on the 20 main tables. Each `_ex` table mirrors the column layout of its corresponding base table.

## Search Indexes

| Table | Index | Definition Summary |
| --- | --- | --- |
| `documents_chunks` | `idx_documents_chunks_document_id` | `idx_documents_chunks_document_id ON documents_chunks USING btree (document_id)` |
| `documents_chunks` | `idx_documents_chunks_document_order` | `idx_documents_chunks_document_order ON documents_chunks USING btree (document_id, chunk_order)` |
| `documents_chunks` | `uq_documents_chunks_document_order` | `UNIQUE uq_documents_chunks_document_order ON documents_chunks USING btree (document_id, chunk_order)` |
| `documents_embeddings` | `idx_documents_embeddings_chunk_id` | `idx_documents_embeddings_chunk_id ON documents_embeddings USING btree (chunk_id)` |
| `documents_embeddings` | `idx_documents_embeddings_source_category` | `idx_documents_embeddings_source_category ON documents_embeddings USING btree (source_type, category)` |
| `documents_embeddings` | `idx_documents_embeddings_vector_cosine` | `idx_documents_embeddings_vector_cosine ON documents_embeddings USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists='100')` |
| `documents_embeddings` | `uq_documents_embeddings_chunk_id` | `UNIQUE uq_documents_embeddings_chunk_id ON documents_embeddings USING btree (chunk_id)` |

## Operation Workflow Tables

`src/operation/workflow/nodes.py`, `src/operation/api/main.py`, and `src/dashboard/workflow/nodes.py` use these tables.

| Phase | Tables |
| --- | --- |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse context | `insight`, `voc_feedback` |
| Policy/outage context | `documents` |
| RAG retrieval | `documents_chunks`, `documents`, `documents_embeddings` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries`, `admin_event_logs` |

Live DB note: these workflow write tables currently have primary keys with no database-side default, so inserts must provide IDs explicitly unless a migration adds defaults: `answer_draft`, `evidence_docs`, `failed_queries`, `final_response`, `safety_results`, `ticket_analysis`. `docs/DB/migrations/20260521_operation_workflow_identity_defaults.sql` is a reference migration for part of this ID strategy.

## Key Relationships

| From | To | On Update | On Delete |
| --- | --- | --- | --- |
| `admin_event_logs.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `answer_draft.analysis_id` | `ticket_analysis.analysis_id` | NO ACTION | CASCADE |
| `answer_draft.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | CASCADE |
| `documents_chunks.document_id` | `documents.documents_id` | NO ACTION | CASCADE |
| `documents_embeddings.chunk_id` | `documents_chunks.chunk_id` | NO ACTION | CASCADE |
| `evidence_docs.draft_id` | `answer_draft.draft_id` | NO ACTION | CASCADE |
| `failed_queries.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `final_response.draft_id` | `answer_draft.draft_id` | NO ACTION | NO ACTION |
| `final_response.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `gacha_logs.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `game_accounts.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `insight.account_id` | `game_accounts.account_id` | NO ACTION | SET NULL |
| `insight.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | CASCADE |
| `insight.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `item_delivery_logs.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `item_delivery_logs.payment_id` | `payments.payment_id` | NO ACTION | SET NULL |
| `notification_logs.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `payments.account_id` | `game_accounts.account_id` | NO ACTION | CASCADE |
| `qa_ticket.account_id` | `game_accounts.account_id` | NO ACTION | SET NULL |
| `qa_ticket.user_id` | `community_users.user_id` | NO ACTION | CASCADE |
| `refunds.payment_id` | `payments.payment_id` | NO ACTION | CASCADE |
| `safety_results.draft_id` | `answer_draft.draft_id` | NO ACTION | CASCADE |
| `ticket_analysis.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | CASCADE |
| `voc_feedback.account_id` | `game_accounts.account_id` | NO ACTION | NO ACTION |
| `voc_feedback.ticket_id` | `qa_ticket.ticket_id` | NO ACTION | NO ACTION |
| `voc_feedback.user_id` | `community_users.user_id` | NO ACTION | NO ACTION |

## Table Details

### `admin_event_logs`

- Purpose: Operation/admin workflow event and error logs
- Estimated Rows: 0
- Primary Key: `log_id`
- Primary Key Default: `nextval('admin_event_logs_log_id_seq'::regclass)`
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `log_id` | `integer` | NO | `nextval('admin_event_logs_log_id_seq'::regclass)` | PK |
| 2 | `ticket_id` | `integer` | YES |  | FK -> `qa_ticket.ticket_id` |
| 3 | `session_id` | `integer` | YES |  |  |
| 4 | `node_name` | `varchar(100)` | YES |  |  |
| 5 | `event_type` | `varchar(100)` | YES |  |  |
| 6 | `category` | `varchar(100)` | YES |  |  |
| 7 | `routing_target` | `varchar(100)` | YES |  |  |
| 8 | `tool_name` | `varchar(100)` | YES |  |  |
| 9 | `status` | `varchar(50)` | YES |  |  |
| 10 | `error_message` | `text` | YES |  |  |
| 11 | `error_category` | `varchar(100)` | YES |  |  |
| 12 | `metadata` | `json` | YES |  |  |
| 13 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `admin_event_logs_pkey`: `UNIQUE admin_event_logs_pkey ON admin_event_logs USING btree (log_id)`

### `answer_draft`

- Purpose: Generated answer drafts for tickets
- Estimated Rows: 97
- Primary Key: `draft_id`
- Primary Key Default: none
- Foreign Keys: `analysis_id` -> `ticket_analysis.analysis_id` (CASCADE), `ticket_id` -> `qa_ticket.ticket_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `draft_id` | `integer` | NO |  | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `analysis_id` | `integer` | NO |  | FK -> `ticket_analysis.analysis_id` |
| 4 | `draft_text` | `text` | YES |  |  |
| 5 | `prompt_version` | `varchar` | YES |  |  |
| 6 | `created_at` | `timestamp` | YES |  |  |

- Indexes:
  - `answer_draft_pkey`: `UNIQUE answer_draft_pkey ON answer_draft USING btree (draft_id)`

### `community_users`

- Purpose: Community user profile data
- Estimated Rows: 6,288
- Primary Key: `user_id`
- Primary Key Default: none
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `user_id` | `integer` | NO |  | PK |
| 2 | `email` | `varchar` | YES |  |  |
| 3 | `nickname` | `varchar` | YES |  |  |
| 4 | `created_at` | `timestamp` | YES |  |  |
| 5 | `user_status` | `varchar` | YES |  |  |
| 6 | `last_login_at` | `timestamp` | YES |  |  |
| 7 | `password_hash` | `text` | YES |  |  |
| 8 | `password_updated_at` | `timestamp` | YES |  |  |

- Indexes:
  - `community_users_pkey`: `UNIQUE community_users_pkey ON community_users USING btree (user_id)`

### `documents`

- Purpose: Source documents for policy, notice, guide, incident, and RAG retrieval
- Estimated Rows: 1,201
- Primary Key: `documents_id`
- Primary Key Default: none
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `documents_id` | `varchar` | NO |  | PK |
| 2 | `source_type` | `varchar` | YES |  |  |
| 3 | `category` | `varchar` | YES |  |  |
| 4 | `title` | `varchar` | YES |  |  |
| 5 | `raw_content` | `text` | YES |  |  |
| 6 | `source_url` | `varchar` | YES |  |  |
| 7 | `published_at` | `timestamp` | YES |  |  |
| 8 | `updated_at` | `timestamp` | YES |  |  |

- Indexes:
  - `documents_pkey`: `UNIQUE documents_pkey ON documents USING btree (documents_id)`

### `documents_chunks`

- Purpose: Searchable chunks split from source documents
- Estimated Rows: 3,864
- Primary Key: `chunk_id`
- Primary Key Default: none
- Unique: `uq_documents_chunks_document_order` (`document_id`, `chunk_order`)
- Foreign Keys: `document_id` -> `documents.documents_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `chunk_id` | `varchar` | NO |  | PK |
| 2 | `document_id` | `varchar` | NO |  | UNIQUE, FK -> `documents.documents_id` |
| 3 | `chunk_text` | `text` | NO |  |  |
| 4 | `chunk_order` | `integer` | NO |  | UNIQUE |
| 5 | `token_count` | `integer` | YES |  |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `documents_chunks_pkey`: `UNIQUE documents_chunks_pkey ON documents_chunks USING btree (chunk_id)`
  - `idx_documents_chunks_document_id`: `idx_documents_chunks_document_id ON documents_chunks USING btree (document_id)`
  - `idx_documents_chunks_document_order`: `idx_documents_chunks_document_order ON documents_chunks USING btree (document_id, chunk_order)`
  - `uq_documents_chunks_document_order`: `UNIQUE uq_documents_chunks_document_order ON documents_chunks USING btree (document_id, chunk_order)`

### `documents_embeddings`

- Purpose: Vector embeddings for document chunks
- Estimated Rows: 3,864
- Primary Key: `embedding_id`
- Primary Key Default: none
- Unique: `uq_documents_embeddings_chunk_id` (`chunk_id`)
- Foreign Keys: `chunk_id` -> `documents_chunks.chunk_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `embedding_id` | `varchar` | NO |  | PK |
| 2 | `chunk_id` | `varchar` | NO |  | UNIQUE, FK -> `documents_chunks.chunk_id` |
| 3 | `embedding_vector` | `vector` | NO |  |  |
| 4 | `embedding_model` | `varchar` | NO |  |  |
| 5 | `source_type` | `varchar` | YES |  |  |
| 6 | `category` | `varchar` | YES |  |  |
| 7 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `documents_embeddings_pkey`: `UNIQUE documents_embeddings_pkey ON documents_embeddings USING btree (embedding_id)`
  - `idx_documents_embeddings_chunk_id`: `idx_documents_embeddings_chunk_id ON documents_embeddings USING btree (chunk_id)`
  - `idx_documents_embeddings_source_category`: `idx_documents_embeddings_source_category ON documents_embeddings USING btree (source_type, category)`
  - `idx_documents_embeddings_vector_cosine`: `idx_documents_embeddings_vector_cosine ON documents_embeddings USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists='100')`
  - `uq_documents_embeddings_chunk_id`: `UNIQUE uq_documents_embeddings_chunk_id ON documents_embeddings USING btree (chunk_id)`

### `evidence_docs`

- Purpose: Retrieved evidence saved for answer drafts
- Estimated Rows: 195
- Primary Key: `evidence_id`
- Primary Key Default: none
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `evidence_id` | `integer` | NO |  | PK |
| 2 | `draft_id` | `integer` | NO |  | FK -> `answer_draft.draft_id` |
| 3 | `source_type` | `varchar` | YES |  |  |
| 4 | `source_id` | `varchar` | YES |  |  |
| 5 | `evidence_text` | `text` | YES |  |  |
| 6 | `relevance_score` | `double precision` | YES |  |  |
| 7 | `retrieval_rank` | `integer` | YES |  |  |

- Indexes:
  - `evidence_docs_pkey`: `UNIQUE evidence_docs_pkey ON evidence_docs USING btree (evidence_id)`

### `failed_queries`

- Purpose: Failed ticket/query processing logs
- Estimated Rows: 9
- Primary Key: `failed_query_id`
- Primary Key Default: none
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `failed_query_id` | `integer` | NO |  | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `query` | `text` | NO |  |  |
| 4 | `category` | `varchar(100)` | YES |  |  |
| 5 | `reason` | `text` | YES |  |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `failed_queries_pkey`: `UNIQUE failed_queries_pkey ON failed_queries USING btree (failed_query_id)`

### `final_response`

- Purpose: Final customer-facing responses
- Estimated Rows: 80
- Primary Key: `response_id`
- Primary Key Default: none
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (NO ACTION), `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `response_id` | `integer` | NO |  | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `draft_id` | `integer` | YES |  | FK -> `answer_draft.draft_id` |
| 4 | `final_text` | `text` | NO |  |  |
| 5 | `safety_action` | `varchar(50)` | YES |  |  |
| 6 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `final_response_pkey`: `UNIQUE final_response_pkey ON final_response USING btree (response_id)`

### `gacha_logs`

- Purpose: Gacha pull history per game account
- Estimated Rows: 5
- Primary Key: `gacha_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `gacha_id` | `integer` | NO |  | PK |
| 2 | `account_id` | `integer` | NO |  | FK -> `game_accounts.account_id` |
| 3 | `banner_name` | `varchar` | YES |  |  |
| 4 | `item_name` | `varchar` | YES |  |  |
| 5 | `item_type` | `varchar` | YES |  |  |
| 6 | `rarity` | `varchar` | YES |  |  |
| 7 | `pity_count` | `integer` | YES |  |  |
| 8 | `pulled_at` | `timestamp` | YES |  |  |

- Indexes:
  - `gacha_logs_pkey`: `UNIQUE gacha_logs_pkey ON gacha_logs USING btree (gacha_id)`

### `game_accounts`

- Purpose: Game account data linked to community users
- Estimated Rows: 6,288
- Primary Key: `account_id`
- Primary Key Default: none
- Foreign Keys: `user_id` -> `community_users.user_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `account_id` | `integer` | NO |  | PK |
| 2 | `user_id` | `integer` | NO |  | FK -> `community_users.user_id` |
| 3 | `game_name` | `varchar` | YES |  |  |
| 4 | `uid` | `varchar` | YES |  |  |
| 5 | `server_region` | `varchar` | YES |  |  |
| 6 | `progression_level` | `integer` | YES |  |  |
| 7 | `account_status` | `varchar` | YES |  |  |
| 8 | `created_at` | `timestamp` | YES |  |  |

- Indexes:
  - `game_accounts_pkey`: `UNIQUE game_accounts_pkey ON game_accounts USING btree (account_id)`

### `insight`

- Purpose: Ticket/user/account-level insight analysis data
- Estimated Rows: 5
- Primary Key: `insight_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (SET NULL), `ticket_id` -> `qa_ticket.ticket_id` (CASCADE), `user_id` -> `community_users.user_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `insight_id` | `integer` | NO |  | PK |
| 2 | `user_id` | `integer` | NO |  | FK -> `community_users.user_id` |
| 3 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 4 | `account_id` | `integer` | YES |  | FK -> `game_accounts.account_id` |
| 5 | `content_summary` | `text` | YES |  |  |
| 6 | `category` | `varchar` | YES |  |  |
| 7 | `sentiment` | `varchar` | YES |  |  |
| 8 | `risk_level` | `varchar` | YES |  |  |
| 9 | `pattern_risk_level` | `varchar` | YES |  |  |
| 10 | `inquiry_created_at` | `timestamp` | YES |  |  |

- Indexes:
  - `insight_pkey`: `UNIQUE insight_pkey ON insight USING btree (insight_id)`

### `item_delivery_logs`

- Purpose: Paid or reward item delivery history
- Estimated Rows: 5
- Primary Key: `delivery_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE), `payment_id` -> `payments.payment_id` (SET NULL)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `delivery_id` | `integer` | NO |  | PK |
| 2 | `payment_id` | `integer` | YES |  | FK -> `payments.payment_id` |
| 3 | `account_id` | `integer` | NO |  | FK -> `game_accounts.account_id` |
| 4 | `source_type` | `varchar` | YES |  |  |
| 5 | `item_name` | `varchar` | YES |  |  |
| 6 | `quantity` | `integer` | YES |  |  |
| 7 | `delivery_status` | `varchar` | YES |  |  |
| 8 | `expected_at` | `timestamp` | YES |  |  |
| 9 | `delivered_at` | `timestamp` | YES |  |  |

- Indexes:
  - `item_delivery_logs_pkey`: `UNIQUE item_delivery_logs_pkey ON item_delivery_logs USING btree (delivery_id)`

### `notification_logs`

- Purpose: Notification send results and errors
- Estimated Rows: 0
- Primary Key: `notification_id`
- Primary Key Default: `nextval('notification_logs_notification_id_seq'::regclass)`
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `notification_id` | `integer` | NO | `nextval('notification_logs_notification_id_seq'::regclass)` | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `channel` | `varchar(50)` | YES |  |  |
| 4 | `status` | `varchar(50)` | YES |  |  |
| 5 | `message` | `text` | YES |  |  |
| 6 | `error_message` | `text` | YES |  |  |
| 7 | `error_category` | `varchar(100)` | YES |  |  |
| 8 | `sent_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `notification_logs_pkey`: `UNIQUE notification_logs_pkey ON notification_logs USING btree (notification_id)`

### `payments`

- Purpose: Payment transaction history
- Estimated Rows: 11
- Primary Key: `payment_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `payment_id` | `integer` | NO |  | PK |
| 2 | `account_id` | `integer` | NO |  | FK -> `game_accounts.account_id` |
| 3 | `product_name` | `varchar` | YES |  |  |
| 4 | `product_type` | `varchar` | YES |  |  |
| 5 | `amount` | `numeric` | YES |  |  |
| 6 | `currency` | `varchar` | YES |  |  |
| 7 | `payment_method` | `varchar` | YES |  |  |
| 8 | `payment_status` | `varchar` | YES |  |  |
| 9 | `transaction_id` | `varchar` | YES |  |  |
| 10 | `paid_at` | `timestamp` | YES |  |  |

- Indexes:
  - `payments_pkey`: `UNIQUE payments_pkey ON payments USING btree (payment_id)`

### `qa_ticket`

- Purpose: Customer inquiry/QA tickets
- Estimated Rows: 9,243
- Primary Key: `ticket_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (SET NULL), `user_id` -> `community_users.user_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `ticket_id` | `integer` | NO |  | PK |
| 2 | `account_id` | `integer` | YES |  | FK -> `game_accounts.account_id` |
| 3 | `user_id` | `integer` | NO |  | FK -> `community_users.user_id` |
| 4 | `title` | `varchar` | YES |  |  |
| 5 | `raw_query` | `text` | YES |  |  |
| 6 | `source_type` | `varchar` | YES |  |  |
| 7 | `status` | `varchar` | YES |  |  |
| 8 | `inquiry_created_at` | `timestamp` | YES |  |  |
| 9 | `session_id` | `integer` | YES |  |  |
| 10 | `responder_type` | `varchar(100)` | YES |  |  |

- Indexes:
  - `qa_ticket_pkey`: `UNIQUE qa_ticket_pkey ON qa_ticket USING btree (ticket_id)`

### `refunds`

- Purpose: Refund request and processing history
- Estimated Rows: 5
- Primary Key: `refund_id`
- Primary Key Default: none
- Foreign Keys: `payment_id` -> `payments.payment_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `refund_id` | `integer` | NO |  | PK |
| 2 | `payment_id` | `integer` | NO |  | FK -> `payments.payment_id` |
| 3 | `refund_status` | `varchar` | YES |  |  |
| 4 | `refund_reason` | `text` | YES |  |  |
| 5 | `requested_at` | `timestamp` | YES |  |  |
| 6 | `processed_at` | `timestamp` | YES |  |  |

- Indexes:
  - `refunds_pkey`: `UNIQUE refunds_pkey ON refunds USING btree (refund_id)`

### `safety_results`

- Purpose: Safety and grounding check results for drafts
- Estimated Rows: 95
- Primary Key: `safety_id`
- Primary Key Default: none
- Foreign Keys: `draft_id` -> `answer_draft.draft_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `safety_id` | `integer` | NO |  | PK |
| 2 | `draft_id` | `integer` | NO |  | FK -> `answer_draft.draft_id` |
| 3 | `hallucination_score` | `double precision` | YES |  |  |
| 4 | `toxicity_score` | `double precision` | YES |  |  |
| 5 | `policy_violation_score` | `double precision` | YES |  |  |
| 6 | `factuality_score` | `double precision` | YES |  |  |
| 7 | `checked_at` | `timestamp` | YES |  |  |
| 8 | `safety_action` | `varchar(100)` | YES |  |  |
| 9 | `safety_reason` | `varchar(255)` | YES |  |  |
| 10 | `retry_count` | `integer` | YES | `0` |  |

- Indexes:
  - `safety_results_pkey`: `UNIQUE safety_results_pkey ON safety_results USING btree (safety_id)`

### `ticket_analysis`

- Purpose: Ticket classification, risk, sentiment, and routing analysis
- Estimated Rows: 118
- Primary Key: `analysis_id`
- Primary Key Default: none
- Foreign Keys: `ticket_id` -> `qa_ticket.ticket_id` (CASCADE)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `analysis_id` | `integer` | NO |  | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `category` | `varchar` | YES |  |  |
| 4 | `responder_type` | `varchar` | YES |  |  |
| 5 | `enriched_query` | `text` | YES |  |  |
| 6 | `risk_level` | `varchar` | YES |  |  |
| 7 | `sentiment` | `varchar` | YES |  |  |
| 8 | `routing_target` | `varchar` | YES |  |  |
| 9 | `summary` | `text` | YES |  |  |
| 10 | `analyzed_at` | `timestamp` | YES |  |  |

- Indexes:
  - `ticket_analysis_pkey`: `UNIQUE ticket_analysis_pkey ON ticket_analysis USING btree (analysis_id)`

### `voc_feedback`

- Purpose: VOC feedback and topic keyword records
- Estimated Rows: 5
- Primary Key: `voc_id`
- Primary Key Default: none
- Foreign Keys: `account_id` -> `game_accounts.account_id` (NO ACTION), `ticket_id` -> `qa_ticket.ticket_id` (NO ACTION), `user_id` -> `community_users.user_id` (NO ACTION)
- Columns:

| # | Column | Data Type | Nullable | Default | Key / Reference |
| ---: | --- | --- | --- | --- | --- |
| 1 | `voc_id` | `integer` | NO |  | PK |
| 2 | `ticket_id` | `integer` | NO |  | FK -> `qa_ticket.ticket_id` |
| 3 | `user_id` | `integer` | NO |  | FK -> `community_users.user_id` |
| 4 | `account_id` | `integer` | YES |  | FK -> `game_accounts.account_id` |
| 5 | `voc_type` | `varchar(100)` | YES |  |  |
| 6 | `sentiment` | `varchar(50)` | YES |  |  |
| 7 | `raw_content` | `text` | NO |  |  |
| 8 | `topic_keywords` | `json` | YES |  |  |
| 9 | `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` |  |

- Indexes:
  - `voc_feedback_pkey`: `UNIQUE voc_feedback_pkey ON voc_feedback USING btree (voc_id)`
