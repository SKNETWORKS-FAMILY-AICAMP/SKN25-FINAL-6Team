 # DB Descriptions

Generated from the live PostgreSQL database on 2026-05-21.

## Basic Info

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | 16.13 |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |

## Table Summary

Row counts are PostgreSQL `pg_stat_user_tables.n_live_tup` estimates.

| Table | Estimated Rows | Purpose |
| --- | ---: | --- |
| `admin_event_logs` | 0 | Operation/admin workflow event and error logs |
| `answer_draft` | 2 | Generated answer drafts for tickets |
| `community_users` | 6,288 | Community user profile data |
| `documents` | 1,201 | Source documents for policy, notice, guide, incident, and RAG retrieval |
| `documents_chunks` | 3,864 | Searchable chunks split from source documents |
| `documents_embeddings` | 3,864 | Vector embeddings for document chunks |
| `evidence_docs` | 2 | Retrieved evidence saved for answer drafts |
| `failed_queries` | 0 | Failed ticket/query processing logs |
| `final_response` | 0 | Final customer-facing responses |
| `gacha_logs` | 5 | Gacha pull history per game account |
| `game_accounts` | 6,288 | Game account data linked to community users |
| `insight` | 5 | Ticket/user/account-level insight analysis data |
| `item_delivery_logs` | 5 | Paid or reward item delivery history |
| `notification_logs` | 0 | Notification send results and errors |
| `payments` | 11 | Payment transaction history |
| `qa_ticket` | 9,221 | Customer inquiry/QA tickets |
| `refunds` | 5 | Refund request and processing history |
| `safety_results` | 2 | Safety and grounding check results for drafts |
| `ticket_analysis` | 3 | Ticket classification, risk, sentiment, and routing analysis |
| `voc_feedback` | 3 | VOC feedback and topic keyword records |

## Data Load Sources

| Source | Target Tables | Notes |
| --- | --- | --- |
| `data/processed/community_users.csv` | `community_users` | 9,221 source rows; upserted by `user_id`, resulting in 6,288 distinct users in the table. |
| `data/processed/qa_ticket.csv` | `qa_ticket` | 9,221 source rows; `source_type` appears twice in the CSV header and `notebooks/insert_processed_data.ipynb` keeps the first occurrence. |
| `notebooks/insert_processed_data.ipynb` | `community_users`, `game_accounts`, `qa_ticket` | Derives 6,288 `game_accounts` rows from distinct non-null `qa_ticket.account_id` to `user_id` mappings before loading tickets. |
| `notebooks/generate_operation_workflow_sample_data.ipynb` | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight`, `voc_feedback` | Adds operation workflow sample context rows used by the LangGraph workflow. |

## Search Indexes

| Table | Index | Definition Summary |
| --- | --- | --- |
| `documents_chunks` | `idx_documents_chunks_document_id` | B-tree index on `document_id`. |
| `documents_chunks` | `idx_documents_chunks_document_order` | B-tree index on `document_id`, `chunk_order`. |
| `documents_chunks` | `uq_documents_chunks_document_order` | Unique B-tree index on `document_id`, `chunk_order`. |
| `documents_embeddings` | `idx_documents_embeddings_chunk_id` | B-tree index on `chunk_id`. |
| `documents_embeddings` | `idx_documents_embeddings_source_category` | B-tree index on `source_type`, `category`. |
| `documents_embeddings` | `idx_documents_embeddings_vector_cosine` | IVFFlat vector cosine index on `embedding_vector` with `lists=100`. |
| `documents_embeddings` | `uq_documents_embeddings_chunk_id` | Unique B-tree index on `chunk_id`. |

## Operation Workflow Tables

`src/operation/workflow/nodes.py` uses these tables:

| Phase | Tables |
| --- | --- |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse context | `insight`, `voc_feedback` |
| Policy/outage context | `documents` |
| RAG retrieval | `documents_chunks`, `documents` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs` |

Live DB note: `ticket_analysis`, `answer_draft`, `evidence_docs`, and `safety_results` do not currently have database-side PK defaults. The workflow assigns those IDs in application code before insert. `final_response` and `notification_logs` still use database defaults.

## Key Relationships

| From | To |
| --- | --- |
| `game_accounts.user_id` | `community_users.user_id` |
| `qa_ticket.user_id` | `community_users.user_id` |
| `qa_ticket.account_id` | `game_accounts.account_id` |
| `payments.account_id` | `game_accounts.account_id` |
| `refunds.payment_id` | `payments.payment_id` |
| `gacha_logs.account_id` | `game_accounts.account_id` |
| `item_delivery_logs.account_id` | `game_accounts.account_id` |
| `item_delivery_logs.payment_id` | `payments.payment_id` |
| `ticket_analysis.ticket_id` | `qa_ticket.ticket_id` |
| `answer_draft.ticket_id` | `qa_ticket.ticket_id` |
| `answer_draft.analysis_id` | `ticket_analysis.analysis_id` |
| `evidence_docs.draft_id` | `answer_draft.draft_id` |
| `safety_results.draft_id` | `answer_draft.draft_id` |
| `final_response.ticket_id` | `qa_ticket.ticket_id` |
| `final_response.draft_id` | `answer_draft.draft_id` |
| `documents_chunks.document_id` | `documents.documents_id` |
| `documents_embeddings.chunk_id` | `documents_chunks.chunk_id` |
| `admin_event_logs.ticket_id` | `qa_ticket.ticket_id` |
| `failed_queries.ticket_id` | `qa_ticket.ticket_id` |
| `notification_logs.ticket_id` | `qa_ticket.ticket_id` |
| `insight.user_id` | `community_users.user_id` |
| `insight.ticket_id` | `qa_ticket.ticket_id` |
| `insight.account_id` | `game_accounts.account_id` |
| `voc_feedback.user_id` | `community_users.user_id` |
| `voc_feedback.ticket_id` | `qa_ticket.ticket_id` |
| `voc_feedback.account_id` | `game_accounts.account_id` |

## Table Details

### `admin_event_logs`

- Primary Key: `log_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `log_id integer NOT NULL DEFAULT nextval('admin_event_logs_log_id_seq'::regclass)`
  - `ticket_id integer NULL`
  - `session_id integer NULL`
  - `node_name varchar(100) NULL`
  - `event_type varchar(100) NULL`
  - `category varchar(100) NULL`
  - `routing_target varchar(100) NULL`
  - `tool_name varchar(100) NULL`
  - `status varchar(50) NULL`
  - `error_message text NULL`
  - `error_category varchar(100) NULL`
  - `metadata json NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `answer_draft`

- Primary Key: `draft_id`
- Live DB behavior: application-assigned integer id, no default sequence in the table definition.
- Foreign Key: `analysis_id` -> `ticket_analysis.analysis_id`, `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `draft_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `analysis_id integer NOT NULL`
  - `draft_text text NULL`
  - `prompt_version varchar NULL`
  - `created_at timestamp NULL`

### `community_users`

- Primary Key: `user_id`
- Columns:
  - `user_id integer NOT NULL`
  - `email varchar NULL`
  - `nickname varchar NULL`
  - `created_at timestamp NULL`
  - `user_status varchar NULL`
  - `last_login_at timestamp NULL`

### `documents`

- Primary Key: `documents_id`
- Columns:
  - `documents_id varchar NOT NULL`
  - `source_type varchar NULL`
  - `category varchar NULL`
  - `title varchar NULL`
  - `raw_content text NULL`
  - `source_url varchar NULL`
  - `published_at timestamp NULL`
  - `updated_at timestamp NULL`

### `documents_chunks`

- Primary Key: `chunk_id`
- Unique: `document_id`, `chunk_order`
- Foreign Key: `document_id` -> `documents.documents_id`
- Columns:
  - `chunk_id varchar NOT NULL`
  - `document_id varchar NOT NULL`
  - `chunk_text text NOT NULL`
  - `chunk_order integer NOT NULL`
  - `token_count integer NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `documents_embeddings`

- Primary Key: `embedding_id`
- Unique: `chunk_id`
- Foreign Key: `chunk_id` -> `documents_chunks.chunk_id`
- Columns:
  - `embedding_id varchar NOT NULL`
  - `chunk_id varchar NOT NULL`
  - `embedding_vector vector NOT NULL`
  - `embedding_model varchar NOT NULL`
  - `source_type varchar NULL`
  - `category varchar NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `evidence_docs`

- Primary Key: `evidence_id`
- Live DB behavior: application-assigned integer id, no default sequence in the table definition.
- Foreign Key: `draft_id` -> `answer_draft.draft_id`
- Columns:
  - `evidence_id integer NOT NULL`
  - `draft_id integer NOT NULL`
  - `source_type varchar NULL`
  - `source_id varchar NULL`
  - `evidence_text text NULL`
  - `relevance_score double precision NULL`
  - `retrieval_rank integer NULL`

### `failed_queries`

- Primary Key: `failed_query_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `failed_query_id integer NOT NULL DEFAULT nextval('failed_queries_failed_query_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `query text NOT NULL`
  - `category varchar(100) NULL`
  - `reason text NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `final_response`

- Primary Key: `response_id`
- Foreign Key: `draft_id` -> `answer_draft.draft_id`, `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `response_id integer NOT NULL DEFAULT nextval('final_response_response_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `draft_id integer NULL`
  - `final_text text NOT NULL`
  - `safety_action varchar(50) NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `gacha_logs`

- Primary Key: `gacha_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`
- Columns:
  - `gacha_id integer NOT NULL`
  - `account_id integer NOT NULL`
  - `banner_name varchar NULL`
  - `item_name varchar NULL`
  - `item_type varchar NULL`
  - `rarity varchar NULL`
  - `pity_count integer NULL`
  - `pulled_at timestamp NULL`

### `game_accounts`

- Primary Key: `account_id`
- Foreign Key: `user_id` -> `community_users.user_id`
- Columns:
  - `account_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `game_name varchar NULL`
  - `uid varchar NULL`
  - `server_region varchar NULL`
  - `progression_level integer NULL`
  - `account_status varchar NULL`
  - `created_at timestamp NULL`

### `insight`

- Primary Key: `insight_id`
- Foreign Keys: `account_id` -> `game_accounts.account_id`, `ticket_id` -> `qa_ticket.ticket_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `insight_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `account_id integer NULL`
  - `content_summary text NULL`
  - `category varchar NULL`
  - `sentiment varchar NULL`
  - `risk_level varchar NULL`
  - `pattern_risk_level varchar NULL`
  - `inquiry_created_at timestamp NULL`

### `item_delivery_logs`

- Primary Key: `delivery_id`
- Foreign Keys: `account_id` -> `game_accounts.account_id`, `payment_id` -> `payments.payment_id`
- Columns:
  - `delivery_id integer NOT NULL`
  - `payment_id integer NULL`
  - `account_id integer NOT NULL`
  - `source_type varchar NULL`
  - `item_name varchar NULL`
  - `quantity integer NULL`
  - `delivery_status varchar NULL`
  - `expected_at timestamp NULL`
  - `delivered_at timestamp NULL`

### `notification_logs`

- Primary Key: `notification_id`
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `notification_id integer NOT NULL DEFAULT nextval('notification_logs_notification_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `channel varchar(50) NULL`
  - `status varchar(50) NULL`
  - `message text NULL`
  - `error_message text NULL`
  - `error_category varchar(100) NULL`
  - `sent_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`

### `payments`

- Primary Key: `payment_id`
- Foreign Key: `account_id` -> `game_accounts.account_id`
- Columns:
  - `payment_id integer NOT NULL`
  - `account_id integer NOT NULL`
  - `product_name varchar NULL`
  - `product_type varchar NULL`
  - `amount numeric NULL`
  - `currency varchar NULL`
  - `payment_method varchar NULL`
  - `payment_status varchar NULL`
  - `transaction_id varchar NULL`
  - `paid_at timestamp NULL`

### `qa_ticket`

- Primary Key: `ticket_id`
- Foreign Keys: `account_id` -> `game_accounts.account_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `ticket_id integer NOT NULL`
  - `account_id integer NULL`
  - `user_id integer NOT NULL`
  - `title varchar NULL`
  - `raw_query text NULL`
  - `source_type varchar NULL`
  - `status varchar NULL`
  - `inquiry_created_at timestamp NULL`
  - `session_id integer NULL`
  - `responder_type varchar(100) NULL`

### `refunds`

- Primary Key: `refund_id`
- Foreign Key: `payment_id` -> `payments.payment_id`
- Columns:
  - `refund_id integer NOT NULL`
  - `payment_id integer NOT NULL`
  - `refund_status varchar NULL`
  - `refund_reason text NULL`
  - `requested_at timestamp NULL`
  - `processed_at timestamp NULL`

### `safety_results`

- Primary Key: `safety_id`
- Live DB behavior: application-assigned integer id, no default sequence in the table definition.
- Foreign Key: `draft_id` -> `answer_draft.draft_id`
- Columns:
  - `safety_id integer NOT NULL`
  - `draft_id integer NOT NULL`
  - `hallucination_score double precision NULL`
  - `toxicity_score double precision NULL`
  - `policy_violation_score double precision NULL`
  - `factuality_score double precision NULL`
  - `checked_at timestamp NULL`
  - `safety_action varchar(100) NULL`
  - `safety_reason varchar(255) NULL`
  - `retry_count integer NULL DEFAULT 0`

### `ticket_analysis`

- Primary Key: `analysis_id`
- Live DB behavior: application-assigned integer id, no default sequence in the table definition.
- Foreign Key: `ticket_id` -> `qa_ticket.ticket_id`
- Columns:
  - `analysis_id integer NOT NULL`
  - `ticket_id integer NOT NULL`
  - `category varchar NULL`
  - `responder_type varchar NULL`
  - `enriched_query text NULL`
  - `risk_level varchar NULL`
  - `sentiment varchar NULL`
  - `routing_target varchar NULL`
  - `summary text NULL`
  - `analyzed_at timestamp NULL`

### `voc_feedback`

- Primary Key: `voc_id`
- Foreign Keys: `account_id` -> `game_accounts.account_id`, `ticket_id` -> `qa_ticket.ticket_id`, `user_id` -> `community_users.user_id`
- Columns:
  - `voc_id integer NOT NULL DEFAULT nextval('voc_feedback_voc_id_seq'::regclass)`
  - `ticket_id integer NOT NULL`
  - `user_id integer NOT NULL`
  - `account_id integer NULL`
  - `voc_type varchar(100) NULL`
  - `sentiment varchar(50) NULL`
  - `raw_content text NOT NULL`
  - `topic_keywords json NULL`
  - `created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP`
