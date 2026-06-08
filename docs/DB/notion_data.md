# Notion-Friendly DB Summary

This document summarizes `db_info.md` and `descriptions.md` for Notion. It reflects the live DB state verified on **2026-06-06**.

## 1. Current State

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit` |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public tables | 39 |
| Public columns | 323 |
| Main tables | 20 |
| `_ex` tables | 19 |

## 2. System Scope

- Admin authentication: `admin_users`
- User/account master data: `community_users`, `game_accounts`
- Customer inquiries: `qa_ticket`
- Operation evidence data: `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- Answer workflow outputs: `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`
- Operation/monitoring: `failed_queries`, `notification_logs`, `admin_event_logs`, `insight`
- Document/RAG store: `documents`, `documents_chunks`, `documents_embeddings`
- Template/source-scale tables: `_ex` versions for most main tables

## 3. Operating Interpretation

The live DB currently has **20 main tables + 19 `_ex` template tables**.

- Main tables represent the current reduced dataset and workflow output state.
- `_ex` tables preserve source-scale or example rows used as regeneration references.
- `admin_users` is a live auth table with no `_ex` mirror.
- `voc_feedback` and `voc_feedback_ex` are not present in the live public schema.

## 4. Main Table Counts

These counts are exact `COUNT(*)` results from the live DB on 2026-06-06.

| Table | Rows | Purpose |
| --- | ---: | --- |
| `admin_event_logs` | 942 | Operation/admin workflow event and error logs |
| `admin_users` | 1 | Administrator/operator login accounts and auth metadata |
| `answer_draft` | 263 | Generated answer drafts for tickets |
| `community_users` | 630 | Community user profile data |
| `documents` | 1,201 | Source documents for policy, notice, guide, incident, and RAG retrieval |
| `documents_chunks` | 2,151 | Searchable chunks split from source documents |
| `documents_embeddings` | 2,151 | Vector embeddings for document chunks |
| `evidence_docs` | 792 | Retrieved evidence saved for answer drafts |
| `failed_queries` | 0 | Failed ticket/query processing logs |
| `final_response` | 493 | Final customer-facing responses |
| `gacha_logs` | 180 | Gacha pull history per game account |
| `game_accounts` | 630 | Game account data linked to community users |
| `insight` | 4 | Ticket/user/account-level insight analysis data |
| `item_delivery_logs` | 140 | Paid or reward item delivery history |
| `notification_logs` | 5 | Notification send results and errors |
| `payments` | 320 | Payment transaction history |
| `qa_ticket` | 1,472 | Customer inquiry/QA tickets |
| `refunds` | 55 | Refund request and processing history |
| `safety_results` | 2 | Safety and grounding check results for drafts |
| `ticket_analysis` | 967 | Ticket classification, risk, sentiment, and routing analysis |

## 5. `_ex` Table Counts

| Table | Rows | Purpose |
| --- | ---: | --- |
| `admin_event_logs_ex` | 3 | Template/example copy of `admin_event_logs` |
| `answer_draft_ex` | 329 | Template/example copy of `answer_draft` |
| `community_users_ex` | 6,288 | Template/source-scale copy of `community_users` |
| `documents_chunks_ex` | 3,864 | Template/example copy of `documents_chunks` |
| `documents_embeddings_ex` | 3,864 | Template/example copy of `documents_embeddings` |
| `documents_ex` | 1,201 | Template/example copy of `documents` |
| `evidence_docs_ex` | 837 | Template/example copy of `evidence_docs` |
| `failed_queries_ex` | 11 | Template/example copy of `failed_queries` |
| `final_response_ex` | 311 | Template/example copy of `final_response` |
| `gacha_logs_ex` | 5 | Template/example copy of `gacha_logs` |
| `game_accounts_ex` | 6,288 | Template/source-scale copy of `game_accounts` |
| `insight_ex` | 5 | Template/example copy of `insight` |
| `item_delivery_logs_ex` | 5 | Template/example copy of `item_delivery_logs` |
| `notification_logs_ex` | 2 | Template/example copy of `notification_logs` |
| `payments_ex` | 11 | Template/example copy of `payments` |
| `qa_ticket_ex` | 9,349 | Template/source-scale copy of `qa_ticket` |
| `refunds_ex` | 5 | Template/example copy of `refunds` |
| `safety_results_ex` | 287 | Template/example copy of `safety_results` |
| `ticket_analysis_ex` | 351 | Template/example copy of `ticket_analysis` |

## 6. Core Reduced Dataset Tables

| Table | Rows | Role |
| --- | ---: | --- |
| `community_users` | 630 | User master data for inquiry owners |
| `game_accounts` | 630 | Game account master data |
| `qa_ticket` | 1,472 | Primary inquiry/post table |
| `payments` | 320 | Operation evidence for payment-related inquiries |
| `refunds` | 55 | Operation evidence for refund-related inquiries |
| `item_delivery_logs` | 140 | Operation evidence for missing or delayed item delivery |
| `gacha_logs` | 180 | Operation evidence for gacha/probability inquiries |

Interpretation:

- `qa_ticket` is the primary inquiry table.
- The other six core tables explain why an inquiry may have occurred.
- Workflow output tables grow as batch jobs and API workflows run.

## 7. Relationship Summary

- `community_users.user_id` parents `game_accounts`, `qa_ticket`, and `insight`.
- `game_accounts.account_id` connects to `payments`, `gacha_logs`, `item_delivery_logs`, and `qa_ticket.account_id`.
- `payments.payment_id` connects to `refunds.payment_id` and `item_delivery_logs.payment_id`.
- The answer workflow follows `qa_ticket -> ticket_analysis -> answer_draft -> safety_results/final_response`.
- The document store follows `documents -> documents_chunks -> documents_embeddings`.
- Admin assignment and event actor references point to `admin_users.admin_id`.

## 8. Workflow Read/Write Map

| Phase | Live Tables |
| --- | --- |
| Admin auth | `admin_users` |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse/VOC context | `insight` |
| Policy/outage context | `documents` |
| RAG retrieval | `documents`, `documents_chunks`, `documents_embeddings` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries`, `admin_event_logs` |

## 9. Current Caveats

### 9.1 Main RAG Store

- `documents`: 1,201 rows
- `documents_chunks`: 2,151 rows
- `documents_embeddings`: 2,151 rows

### 9.2 Workflow Output State

| Table | Rows |
| --- | ---: |
| `ticket_analysis` | 967 |
| `answer_draft` | 263 |
| `evidence_docs` | 792 |
| `safety_results` | 2 |
| `final_response` | 493 |
| `failed_queries` | 0 |
| `admin_event_logs` | 942 |
| `notification_logs` | 5 |
| `insight` | 4 |

### 9.3 `_ex` Tables Are Templates

- `_ex` tables are not the active operation target.
- Analysis and demos should not mix main table rows with `_ex` rows unless explicitly comparing live vs template data.
- `voc_feedback` appears in some older docs, but it is not a live public table at this verification point.

## 10. Data Generation References

- `docs/data_generation/plan.md`: reduced scope, target counts, hard-case quota, and table policies
- `docs/data_generation/paper_description.md`: methodology rationale, seed expansion, hard-case supplementation, and privacy/style considerations
- `docs/data_generation/repopulate_reduced_dataset.py`: repopulates the seven core reduced tables from `_ex` templates
- `docs/data_generation/ppt_data_generation_narrative.md`: presentation-facing methodology summary

## 11. Main Schema ERD

```smalltalk
Table admin_users {
  admin_id integer [pk]
  login_id varchar(100)
  password_hash text
  display_name varchar(100)
  role varchar(30)
  status varchar(30)
  last_login_at timestamp [null]
  password_updated_at timestamp
  created_at timestamp
}

Table community_users {
  user_id integer [pk]
  email varchar [null]
  nickname varchar [null]
  created_at timestamp [null]
  user_status varchar [null]
  last_login_at timestamp [null]
  password_hash text [null]
  password_updated_at timestamp [null]
}

Table game_accounts {
  account_id integer [pk]
  user_id integer [ref: > community_users.user_id]
  game_name varchar [null]
  uid varchar [null]
  server_region varchar [null]
  progression_level integer [null]
  account_status varchar [null]
  created_at timestamp [null]
}

Table qa_ticket {
  ticket_id integer [pk]
  account_id integer [ref: > game_accounts.account_id, null]
  user_id integer [ref: > community_users.user_id]
  title varchar [null]
  raw_query text [null]
  source_type varchar [null]
  status varchar [null]
  inquiry_created_at timestamp [null]
  session_id integer [null]
  responder_type varchar(100) [null]
  assignee_id varchar [null]
  assignee_admin_id integer [ref: > admin_users.admin_id, null]
}
```

## 12. Workflow/RAG Schema Notes

- `ticket_analysis.ticket_id` references `qa_ticket.ticket_id`.
- `answer_draft.ticket_id` references `qa_ticket.ticket_id`.
- `answer_draft.analysis_id` references `ticket_analysis.analysis_id`.
- `evidence_docs.draft_id` and `safety_results.draft_id` reference `answer_draft.draft_id`.
- `final_response.ticket_id` references `qa_ticket.ticket_id`.
- `final_response.draft_id` optionally references `answer_draft.draft_id`.
- `admin_event_logs.actor_admin_id` references `admin_users.admin_id`.
- `documents_chunks.document_id` references `documents.documents_id`.
- `documents_embeddings.chunk_id` references `documents_chunks.chunk_id`.

## 13. Data Source Notes

| Source | Target Tables | Notes |
| --- | --- | --- |
| `data/processed/community_users.csv` | `community_users` | User seed data |
| `data/processed/qa_ticket.csv` | `qa_ticket` | Inquiry/post seed data |
| `notebooks/insert_processed_data.ipynb` | `community_users`, `game_accounts`, `qa_ticket` | Historical ingestion notebook |
| `notebooks/generate_operation_workflow_sample_data.ipynb` | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight` | Historical operation context sample generation; older notes may mention `voc_feedback`, which is not present in the live schema. |
| `docs/data_generation/repopulate_reduced_dataset.py` | `community_users`, `game_accounts`, `qa_ticket`, `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` | Rebuilds the reduced dataset from `_ex` template tables |
