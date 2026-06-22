# DB Notion Summary

Last verified from the live database on 2026-06-18.

## Basic Facts

- DBMS: PostgreSQL 16.14
- Host: `100.97.235.15`
- Database: `game_cs`
- User: `game_cs_user`
- Schema: `public`
- Extensions: `plpgsql 1.0`, `vector 0.6.0`
- Public tables: 19
- Public columns: 151

## Current Live-Schema Notes

- The live document/RAG store is `documents -> documents_chunks -> documents_embeddings`.
- The live `public` schema has no `_ex` mirror tables.
- Older repo docs may still mention `sj_documents`, `test_documents_chunks`, or `test_documents_embeddings_large/small`; those names are not in the live schema as of 2026-06-18.
- `apps/weekly_report/db/top_requests.py` optionally queries `voc_feedback.topic_keywords`, but `voc_feedback` is not in the live schema snapshot documented here.
- Workflow write tables `answer_draft`, `evidence_docs`, `failed_queries`, `final_response`, `safety_results`, and `ticket_analysis` use database-generated identity PKs.

## Table Summary

| Table | Exact Rows | Purpose |
| --- | ---: | --- |
| `admin_users` | 10 | Administrator/operator login accounts and auth metadata |
| `answer_draft` | 30 | Generated answer drafts for tickets |
| `community_users` | 1,500 | Community user profile data |
| `documents` | 1,068 | Source documents used by the current RAG corpus |
| `documents_chunks` | 5,068 | Searchable chunks for the current RAG corpus |
| `documents_embeddings` | 5,068 | Vector embeddings for document chunks |
| `evidence_docs` | 106 | Retrieved evidence saved for answer drafts |
| `failed_queries` | 3 | Failed ticket/query processing logs |
| `final_response` | 13 | Final customer-facing responses |
| `gacha_logs` | 25,000 | Gacha pull history per game account |
| `game_accounts` | 1,500 | Game account data linked to community users |
| `insight` | 0 | Ticket/user/account-level insight analysis data |
| `item_delivery_logs` | 10,000 | Paid or reward item delivery history |
| `notification_logs` | 0 | Notification send results and errors |
| `payments` | 5,000 | Payment transaction history |
| `qa_ticket` | 9,257 | Customer inquiry/QA tickets |
| `refunds` | 300 | Refund request and processing history |
| `safety_results` | 26 | Safety and grounding check results for drafts |
| `ticket_analysis` | 0 | Ticket classification, risk, sentiment, and routing analysis |

## Workflow Map

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

## References

- Detailed schema: `docs/DB/descriptions.md`
- Connection and verification notes: `docs/DB/db_info.md`
