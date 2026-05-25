# Notion DB Summary

`db_info.md` and `descriptions.md` were last verified against the live PostgreSQL database on 2026-05-24. This document is a Notion-friendly summary of the same schema, table roles, relationships, and example records.

## Basic Info

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)` |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public Tables | 20 |
| Public Columns | 165 |

## System Scope

- Community and game account master data: `community_users`, `game_accounts`
- Customer inquiry data: `qa_ticket`
- Payment and operation context: `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- Analysis and response workflow: `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`
- Monitoring and operational support: `failed_queries`, `notification_logs`, `admin_event_logs`, `insight`, `voc_feedback`
- RAG document store: `documents`, `documents_chunks`, `documents_embeddings`

## RDBMS ERD

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

Table failed_queries {
  failed_query_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  query text
  category varchar
  reason text
  created_at datetime
}

Table notification_logs {
  notification_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  channel varchar
  status varchar
  message text
  error_message text
  error_category varchar
  sent_at datetime
}

Table admin_event_logs {
  log_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id, null]
  session_id int
  node_name varchar
  event_type varchar
  category varchar
  routing_target varchar
  tool_name varchar
  status varchar
  error_message text
  error_category varchar
  metadata json
  created_at datetime
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

Table insight {
  insight_id int [pk]
  user_id int [ref: > community_users.user_id]
  ticket_id int [ref: > qa_ticket.ticket_id]
  account_id int [ref: > game_accounts.account_id, null]
  content_summary text
  category varchar
  sentiment varchar
  risk_level varchar
  pattern_risk_level varchar
  inquiry_created_at datetime
}

Table voc_feedback {
  voc_id int [pk]
  ticket_id int [ref: > qa_ticket.ticket_id]
  user_id int [ref: > community_users.user_id]
  account_id int [ref: > game_accounts.account_id, null]
  voc_type varchar
  sentiment varchar
  raw_content text
  topic_keywords json
  created_at datetime
}
```

## Vector / RAG ERD

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

## Table Summary

| Table | Estimated Rows | Purpose |
| --- | ---: | --- |
| `admin_event_logs` | 0 | Operation/admin workflow event and error logs |
| `answer_draft` | 97 | Generated answer drafts for tickets |
| `community_users` | 6,288 | Community user profile data |
| `documents` | 1,201 | Source documents for policy, notice, guide, incident, and retrieval |
| `documents_chunks` | 3,864 | Searchable chunks split from source documents |
| `documents_embeddings` | 3,864 | Vector embeddings for document chunks |
| `evidence_docs` | 195 | Retrieved evidence attached to answer drafts |
| `failed_queries` | 9 | Failed ticket/query processing logs |
| `final_response` | 80 | Final customer-facing responses |
| `gacha_logs` | 5 | Gacha pull history |
| `game_accounts` | 6,288 | Game account data linked to community users |
| `insight` | 5 | Ticket/user/account-level insight analysis data |
| `item_delivery_logs` | 5 | Paid or reward item delivery history |
| `notification_logs` | 0 | Notification send results and errors |
| `payments` | 11 | Payment transaction history |
| `qa_ticket` | 9,243 | Customer inquiry and QA tickets |
| `refunds` | 5 | Refund request and processing history |
| `safety_results` | 95 | Safety and grounding check results |
| `ticket_analysis` | 118 | Ticket classification, risk, sentiment, and routing analysis |
| `voc_feedback` | 5 | VOC feedback and topic keyword records |

## Workflow Read/Write Map

| Phase | Main Tables |
| --- | --- |
| Ticket load | `qa_ticket`, `community_users`, `game_accounts` |
| Payment context | `payments`, `game_accounts` |
| Refund context | `refunds`, `payments`, `game_accounts` |
| Item delivery context | `item_delivery_logs`, `game_accounts` |
| Gacha context | `gacha_logs`, `game_accounts` |
| Abuse / VOC context | `insight`, `voc_feedback` |
| Policy / outage context | `documents` |
| RAG retrieval | `documents`, `documents_chunks`, `documents_embeddings` |
| Workflow writes | `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `failed_queries`, `admin_event_logs` |

## Key Relationship Notes

- `community_users.user_id` is the parent key for both `game_accounts` and `qa_ticket`.
- `qa_ticket.account_id` is nullable and uses `SET NULL` on delete from `game_accounts`.
- `ticket_analysis`, `answer_draft`, `evidence_docs`, and `safety_results` form the core answer-generation chain.
- `final_response` connects the customer-facing result back to both `qa_ticket` and `answer_draft`.
- `documents` -> `documents_chunks` -> `documents_embeddings` is the RAG storage chain.
- `insight` and `voc_feedback` provide operational review context beyond direct ticket handling.

## ID / Insert Caution

These workflow write tables currently have no database-side primary-key default, so inserts must supply IDs explicitly unless a migration adds defaults:

- `answer_draft`
- `evidence_docs`
- `failed_queries`
- `final_response`
- `safety_results`
- `ticket_analysis`

Auto-increment defaults currently exist for:

- `admin_event_logs.log_id`
- `notification_logs.notification_id`

## Example Records

### `community_users`

| user_id | email | nickname | created_at | user_status | last_login_at |
| ---: | --- | --- | --- | --- | --- |
| 1 | `user1@game.com` | `FireMage` | `2026-05-01 09:00:00` | `active` | `2026-05-11 22:10:00` |
| 2 | `user2@game.com` | `ShadowFox` | `2026-05-02 11:20:00` | `suspended` | `2026-05-10 18:00:00` |

### `game_accounts`

| account_id | user_id | game_name | uid | server_region | progression_level | account_status | created_at |
| ---: | ---: | --- | --- | --- | ---: | --- | --- |
| 101 | 1 | `genshin impact` | `8123456` | `KR` | 57 | `active` | `2026-05-01 09:10:00` |
| 102 | 2 | `starrail` | `18789012` | `JP` | 34 | `active` | `2026-05-02 11:30:00` |

### `qa_ticket`

| ticket_id | account_id | user_id | title | raw_query | source_type | status | inquiry_created_at | session_id | responder_type |
| ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- |
| 1001 | 101 | 1 | `결제 후 아이템이 지급되지 않았어요` | `결제는 완료됐는데 구매한 아이템이 지급되지 않았습니다.` | `community` | `open` | `2026-05-11 10:00:00` | 501 | `AI` |
| 1002 | 102 | 2 | `가챠 결과 문의` | `가챠 결과가 이상한 것 같아서 확인 요청드립니다.` | `chatbot` | `pending` | `2026-05-11 11:30:00` | 502 | `human` |

### `ticket_analysis`

| analysis_id | ticket_id | category | responder_type | enriched_query | risk_level | sentiment | routing_target | summary | analyzed_at |
| ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 5001 | 1001 | `payment` | `AI` | `Likely post-payment non-delivery case; check payment and delivery logs.` | `HIGH` | `negative` | `urgent_alert` | `Possible successful-payment but item-missing issue.` | `2026-05-11 10:03:00` |
| 5002 | 1002 | `gacha` | `human` | `Requires comparison between gacha outcome and published policy documents.` | `LOW` | `neutral` | `rag_reply` | `Policy verification inquiry for gacha outcome.` | `2026-05-11 11:35:00` |

### `payments`

| payment_id | account_id | product_name | product_type | amount | currency | payment_method | payment_status | transaction_id | paid_at |
| ---: | ---: | --- | --- | ---: | --- | --- | --- | --- | --- |
| 7001 | 101 | `Starter Package` | `package` | 9900 | `KRW` | `card` | `success` | `TXN12345` | `2026-05-11 09:55:00` |
| 7002 | 102 | `200 Diamonds` | `currency` | 55000 | `KRW` | `google_pay` | `fail` | `TXN67890` | `2026-05-11 11:00:00` |

### `refunds`

| refund_id | payment_id | refund_status | refund_reason | requested_at | processed_at |
| ---: | ---: | --- | --- | --- | --- |
| 9501 | 7001 | `pending` | `Item not delivered` | `2026-05-11 10:20:00` |  |
| 9502 | 7002 | `completed` | `Verify whether a failed payment was still charged` | `2026-05-11 11:20:00` | `2026-05-11 16:30:00` |

### `item_delivery_logs`

| delivery_id | payment_id | account_id | source_type | item_name | quantity | delivery_status | expected_at | delivered_at |
| ---: | ---: | ---: | --- | --- | ---: | --- | --- | --- |
| 8001 | 7001 | 101 | `payment_reward` | `Starter Package Box` | 1 | `fail` | `2026-05-11 10:01:00` |  |
| 8002 |  | 102 | `event_reward` | `SSR Exchange Ticket` | 3 | `delivered` | `2026-05-10 18:00:00` | `2026-05-10 18:01:00` |

### `gacha_logs`

| gacha_id | account_id | banner_name | item_name | item_type | rarity | pity_count | pulled_at |
| ---: | ---: | --- | --- | --- | --- | ---: | --- |
| 9001 | 101 | `Spring Festival Pickup` | `Meteor Blade` | `weapon` | `4-star` | 72 | `2026-05-11 08:00:00` |
| 9002 | 102 | `New Character Pickup` | `Starlight Mage` | `character` | `5-star` | 34 | `2026-05-11 11:10:00` |

### `answer_draft`

| draft_id | ticket_id | analysis_id | draft_text | prompt_version | created_at |
| ---: | ---: | ---: | --- | --- | --- |
| 3001 | 1001 | 5001 | `결제 내역과 지급 상태를 확인한 뒤 보상 또는 복구 절차를 안내드리겠습니다.` | `v2_payment_prompt` | `2026-05-11 10:05:00` |
| 3002 | 1002 | 5002 | `가챠 정책과 공개 확률 기준을 확인한 뒤 관련 내용을 안내드리겠습니다.` | `v1_gacha_prompt` | `2026-05-11 11:40:00` |

### `evidence_docs`

| evidence_id | draft_id | source_type | source_id | evidence_text | relevance_score | retrieval_rank |
| ---: | ---: | --- | --- | --- | ---: | ---: |
| 4001 | 3001 | `FAQ` | `FAQ-101` | `Purchased items are normally delivered within five minutes after payment.` | 0.94 | 1 |
| 4002 | 3002 | `NOTICE` | `NOTICE-77` | `Gacha probability and reward policies follow the published notice.` | 0.89 | 1 |

### `safety_results`

| safety_id | draft_id | hallucination_score | toxicity_score | policy_violation_score | factuality_score | checked_at | safety_action | safety_reason | retry_count |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 6001 | 3001 | 0.03 | 0.00 | 0.01 | 0.98 | `2026-05-11 10:05:30` | `allow` | `grounded_with_payment_context` | 0 |
| 6002 | 3002 | 0.07 | 0.00 | 0.00 | 0.95 | `2026-05-11 11:40:20` | `allow` | `grounded_with_notice_evidence` | 0 |

### `final_response`

| response_id | ticket_id | draft_id | final_text | safety_action | created_at |
| ---: | ---: | ---: | --- | --- | --- |
| 2001 | 1001 | 3001 | `결제는 확인되었으며 지급 로그를 재점검한 뒤 후속 조치를 안내드리겠습니다.` | `allow` | `2026-05-11 10:06:00` |
| 2002 | 1002 | 3002 | `가챠 결과는 공개 확률 정책과 함께 검토하여 안내드리겠습니다.` | `allow` | `2026-05-11 11:41:00` |

### `insight`

| insight_id | user_id | ticket_id | account_id | content_summary | category | sentiment | risk_level | pattern_risk_level | inquiry_created_at |
| ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| 11001 | 1 | 1001 | 101 | `Repeated growth in item-not-delivered complaints after payment.` | `payment` | `negative` | `HIGH` | `CRITICAL` | `2026-05-11 10:00:00` |
| 11002 | 2 | 1002 | 102 | `Increasing trend of inquiries about gacha probability and fairness.` | `gacha` | `neutral` | `LOW` | `MEDIUM` | `2026-05-11 11:30:00` |

### `voc_feedback`

| voc_id | ticket_id | user_id | account_id | voc_type | sentiment | raw_content | topic_keywords | created_at |
| ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| 12001 | 1001 | 1 | 101 | `complaint` | `negative` | `결제 후 아이템이 바로 지급되지 않아 불편합니다.` | `["payment","delivery","delay"]` | `2026-05-11 10:10:00` |
| 12002 | 1002 | 2 | 102 | `question` | `neutral` | `가챠 결과를 공개된 확률 공지 기준으로 확인하고 싶습니다.` | `["gacha","probability","notice"]` | `2026-05-11 11:45:00` |

### `documents`

| documents_id | source_type | category | title | source_url | published_at |
| --- | --- | --- | --- | --- | --- |
| `FAQ-101` | `FAQ` | `payment` | `Payment error and non-delivery response guide` | `https://docs.game.com/faq/payment-101` | `2026-05-01 10:00:00` |
| `NOTICE-77` | `NOTICE` | `gacha` | `Gacha probability and reward policy notice` | `https://docs.game.com/notice/gacha-77` | `2026-05-03 09:00:00` |

### `documents_chunks`

| chunk_id | document_id | chunk_order | token_count | chunk_text |
| --- | --- | ---: | ---: | --- |
| `FAQ-101-1` | `FAQ-101` | 1 | 32 | `Purchased items are normally delivered within five minutes after payment.` |
| `NOTICE-77-1` | `NOTICE-77` | 1 | 25 | `Gacha probability and reward policies follow the published notice.` |

### `documents_embeddings`

| embedding_id | chunk_id | embedding_model | source_type | category | created_at |
| --- | --- | --- | --- | --- | --- |
| `FAQ-101-1-E` | `FAQ-101-1` | `bge-m3` | `FAQ` | `payment` | `2026-05-01 10:06:00` |
| `NOTICE-77-1-E` | `NOTICE-77-1` | `bge-m3` | `NOTICE` | `gacha` | `2026-05-03 09:11:00` |

## Data Source Notes

| Source | Target Tables | Notes |
| --- | --- | --- |
| `data/processed/community_users.csv` | `community_users` | 9,221 source rows; upserted by `user_id`, resulting in 6,288 distinct users |
| `data/processed/qa_ticket.csv` | `qa_ticket` | Duplicate `source_type` appears in the CSV header; the insert notebook keeps the first occurrence |
| `notebooks/insert_processed_data.ipynb` | `community_users`, `game_accounts`, `qa_ticket` | Builds `game_accounts` from distinct non-null `qa_ticket.account_id` to `user_id` mappings before ticket insert |
| `notebooks/generate_operation_workflow_sample_data.ipynb` | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`, `insight`, `voc_feedback` | Generates sample operation context data used by the workflow |
