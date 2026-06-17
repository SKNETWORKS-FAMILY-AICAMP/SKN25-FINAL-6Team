# Notion-Friendly DB Summary

This document summarizes `db_info.md` and `descriptions.md` for Notion. It reflects the live DB state verified on **2026-06-17**.

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
| Public tables | 20 |
| Public columns | 158 |
| `_ex` tables | 0 |

## 2. System Scope

- Admin authentication: `admin_users`
- User/account master data: `community_users`, `game_accounts`
- Customer inquiries: `qa_ticket`
- Operation evidence data: `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- Answer workflow outputs: `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`
- Operation/monitoring: `failed_queries`, `notification_logs`, `insight`
- Document/RAG store: `sj_documents`, `test_documents_chunks`, `test_documents_embeddings_large`, `test_documents_embeddings_small`

## 3. Operating Interpretation

The live DB currently has **20 public tables and no `_ex` mirror tables**.

- The live schema differs from older reduced-dataset docs that described `_ex` tables.
- The active RAG corpus tables are `sj_documents -> test_documents_chunks -> test_documents_embeddings_large/small`.
- Older docs and some code still reference `documents`, `documents_chunks`, and `documents_embeddings`; those table names are absent from the live `public` schema at this verification point.

## 4. Live Table Counts

These counts are exact `COUNT(*)` results from the live DB on 2026-06-17.

| Table | Rows | Purpose |
| --- | ---: | --- |
| `admin_users` | 10 | Administrator/operator login accounts and auth metadata |
| `community_users` | 1,500 | Community user profile data |
| `game_accounts` | 1,500 | Game account data linked to community users |
| `qa_ticket` | 9,228 | Customer inquiry/QA tickets |
| `payments` | 5,000 | Payment transaction history |
| `refunds` | 300 | Refund request and processing history |
| `item_delivery_logs` | 10,000 | Paid or reward item delivery history |
| `gacha_logs` | 25,000 | Gacha pull history per game account |
| `ticket_analysis` | 0 | Ticket classification, risk, sentiment, and routing analysis |
| `answer_draft` | 4 | Generated answer drafts for tickets |
| `evidence_docs` | 16 | Retrieved evidence saved for answer drafts |
| `safety_results` | 4 | Safety and grounding check results for drafts |
| `final_response` | 0 | Final customer-facing responses |
| `failed_queries` | 0 | Failed ticket/query processing logs |
| `notification_logs` | 0 | Notification send results and errors |
| `insight` | 0 | Ticket/user/account-level insight analysis data |
| `sj_documents` | 1,068 | Source documents used by the current RAG corpus |
| `test_documents_chunks` | 5,068 | Searchable chunks for the current RAG corpus |
| `test_documents_embeddings_large` | 5,068 | Large-model vector embeddings for document chunks |
| `test_documents_embeddings_small` | 5,068 | Small-model vector embeddings for document chunks |

## 5. Core Operational Tables

| Table | Rows | Role |
| --- | ---: | --- |
| `community_users` | 1,500 | User master data for inquiry owners |
| `game_accounts` | 1,500 | Game account master data |
| `qa_ticket` | 9,228 | Primary inquiry/post table |
| `payments` | 5,000 | Operation evidence for payment-related inquiries |
| `refunds` | 300 | Operation evidence for refund-related inquiries |
| `item_delivery_logs` | 10,000 | Operation evidence for missing or delayed item delivery |
| `gacha_logs` | 25,000 | Operation evidence for gacha/probability inquiries |

Interpretation:

- `qa_ticket` is the primary inquiry table.
- The payment/refund/item/gacha tables provide operation evidence used to answer or investigate tickets.
- Workflow output tables are currently sparse compared with the ticket corpus and appear to reflect only a small portion of completed runs.

## 6. Relationship Summary

- `community_users.user_id` parents `game_accounts`, `qa_ticket`, and `insight`.
- `game_accounts.account_id` connects to `payments`, `gacha_logs`, `item_delivery_logs`, `qa_ticket.account_id`, and `insight.account_id`.
- `payments.payment_id` connects to `refunds.payment_id` and `item_delivery_logs.payment_id`.
- The answer workflow follows `qa_ticket -> ticket_analysis -> answer_draft -> safety_results/final_response`.
- The live document store follows `sj_documents -> test_documents_chunks -> test_documents_embeddings_large/small`.

## 7. Workflow Read/Write Map

| Phase | Live Tables |
| --- | --- |
| Admin auth | `admin_users` |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `payments`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse/VOC context | `insight` |
| RAG source | `sj_documents` |
| RAG retrieval | `test_documents_chunks`, `test_documents_embeddings_large`, `test_documents_embeddings_small` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries` |

## 8. Current Caveats

### 8.1 RAG Store

- `sj_documents`: 1,068 rows
- `test_documents_chunks`: 5,068 rows
- `test_documents_embeddings_large`: 5,068 rows
- `test_documents_embeddings_small`: 5,068 rows

### 8.2 Workflow Output State

| Table | Rows |
| --- | ---: |
| `ticket_analysis` | 0 |
| `answer_draft` | 4 |
| `evidence_docs` | 16 |
| `safety_results` | 4 |
| `final_response` | 0 |
| `failed_queries` | 0 |
| `notification_logs` | 0 |
| `insight` | 0 |

### 8.3 Historical Reference Gap

- The repo still contains `docs/data_generation/*` and older DB docs that describe `_ex` tables and `documents*` tables.
- Those references remain useful as project history, but they should not be treated as live-schema facts without re-checking PostgreSQL.

## 9. Main Schema ERD

```smalltalk
Table community_users {
  user_id integer [pk]
}

Table game_accounts {
  account_id integer [pk]
  user_id integer [ref: > community_users.user_id]
}

Table qa_ticket {
  ticket_id integer [pk]
  account_id integer [ref: > game_accounts.account_id, null]
  user_id integer [ref: > community_users.user_id]
  assignee_admin_id integer [ref: > admin_users.admin_id, null]
}

Table ticket_analysis {
  analysis_id integer [pk]
  ticket_id integer [ref: > qa_ticket.ticket_id]
}

Table answer_draft {
  draft_id integer [pk]
  ticket_id integer [ref: > qa_ticket.ticket_id]
  analysis_id integer [ref: > ticket_analysis.analysis_id, null]
}

Table evidence_docs {
  evidence_id integer [pk]
  draft_id integer [ref: > answer_draft.draft_id]
}

Table safety_results {
  safety_id integer [pk]
  draft_id integer [ref: > answer_draft.draft_id]
}

Table final_response {
  response_id integer [pk]
  ticket_id integer [ref: > qa_ticket.ticket_id]
  draft_id integer [ref: > answer_draft.draft_id, null]
}

Table sj_documents {
  document_id varchar [pk]
}

Table test_documents_chunks {
  chunk_id varchar [pk]
  document_id varchar [ref: > sj_documents.document_id]
}

Table test_documents_embeddings_large {
  embedding_id varchar [pk]
  chunk_id varchar [ref: > test_documents_chunks.chunk_id]
}

Table test_documents_embeddings_small {
  embedding_id varchar [pk]
  chunk_id varchar [ref: > test_documents_chunks.chunk_id]
}
```

## 10. Workflow/RAG Schema Notes

- `ticket_analysis.ticket_id` references `qa_ticket.ticket_id`.
- `answer_draft.ticket_id` references `qa_ticket.ticket_id`.
- `answer_draft.analysis_id` references `ticket_analysis.analysis_id`.
- `evidence_docs.draft_id` and `safety_results.draft_id` reference `answer_draft.draft_id`.
- `final_response.ticket_id` references `qa_ticket.ticket_id`.
- `final_response.draft_id` optionally references `answer_draft.draft_id`.
- `test_documents_chunks.document_id` references `sj_documents.document_id`.
- `test_documents_embeddings_large.chunk_id` and `test_documents_embeddings_small.chunk_id` reference `test_documents_chunks.chunk_id`.

## 11. Data Source Notes

| Source | Notes |
| --- | --- |
| Live PostgreSQL `public` schema | Source of truth for this document. |
| `docs/data_generation/*` | Historical/research references; does not match the current live schema one-to-one. |
| Repo code under `apps/` and `packages/` | Some modules still reference older `documents*` names and should be validated separately against the live DB. |
