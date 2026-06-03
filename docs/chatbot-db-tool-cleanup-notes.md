# Chatbot DB Tool Cleanup Notes

## Scope

This note is for analysis only. It does not change chatbot runtime code.

Analysis scope:

- write tool / read tool 분류
- DB tool과 repository 호출 구조 확인
- repository 직접 호출 전환 후보 정리
- 통합 단계에서 실제 리팩토링할 방향 기록

## Current Structure

현재 `apps/chatbot/backend/tools/db_tools.py`는 LangChain `@tool` wrapper로 DB read/write 기능을 노출한다.

```text
agent/node
-> db_tools.py tool
-> repository/*
-> common.db.connection.db_connection
```

다만 모든 DB 접근이 tool을 통해서만 이루어지는 것은 아니다.

- 일부 agent policy는 DB read tool을 LLM tool로 등록한다.
- 일부 node는 tool을 직접 `.invoke()`한다.
- 일부 service/agent는 repository를 직접 호출한다.

## Registered Agent Tools

`apps/chatbot/backend/generation/policies.py` 기준:

| Agent | Tools |
| --- | --- |
| payment_agent | `collect_user_payment_context` |
| bug_agent | `read_gacha_logs`, `read_item_delivery_logs` |
| faq_agent | 없음 |

현재 FAQ agent는 vector search를 tool로 호출하지 않고 `generation/faq_agent.py`에서 RAG pipeline을 직접 실행한다.

## Read Tools

현재 DB read 성격의 tool:

| Tool | Repository | 용도 |
| --- | --- | --- |
| `verify_user_login` | `account_repository.verify_user_login` | 로그인 검증 |
| `read_payments` | `operation_log_repository.read_payments_by_account` | 결제 내역 조회 |
| `read_refunds` | `operation_log_repository.read_refunds_by_payment` | 환불 조회 |
| `read_item_delivery_logs` | `operation_log_repository.read_item_delivery_logs_by_account` | 아이템 지급 로그 조회 |
| `read_gacha_logs` | `operation_log_repository.read_gacha_logs_by_account` | 가챠 로그 조회 |
| `collect_user_payment_context` | `operation_log_repository.collect_payment_context_by_user` | 결제/환불/아이템/가챠 context 통합 조회 |

현재 직접 repository 호출:

- `payment_agent.py`는 `collect_payment_context_by_user()`를 직접 호출한다.
- `account_service.py`는 로그인/서버 region 조회를 repository에서 직접 호출한다.
- notification 관련 코드는 notification repository를 직접 호출한다.

## Write Tools

현재 DB write 성격의 tool:

| Tool | Repository | 용도 |
| --- | --- | --- |
| `write_qa_ticket` | `ticket_repository.save_qa_ticket` | QA 티켓 저장 |
| `write_answer_draft` | `draft_repository.save_answer_draft` | 답변 초안 저장 |
| `write_evidence_docs` | `draft_repository.save_evidence_docs` | 근거 문서 저장 |
| `write_safety_results` | `safety_repository.save_safety_results` | safety 평가 저장 |
| `write_final_response` | `final_response_repository.save_final_response` | 최종 답변 저장 |
| `write_failed_query` | `failed_query_repository.save_failed_query` | FAQ 실패 쿼리 저장 |
| `update_qa_ticket_status` | `ticket_repository.update_qa_ticket_status` | QA 티켓 상태 변경 |

현재 node에서 직접 `.invoke()`하는 write tool:

- `ticket_preprocess.py`: `write_qa_ticket`
- `persistence.py`: `write_answer_draft`, `write_evidence_docs`
- `safety_layer.py`: `write_safety_results`
- `final_response.py`: `write_final_response`, `update_qa_ticket_status`
- `faq_agent.py`: `write_failed_query`

## Cleanup Candidates

### 1. Node 내부 write는 repository 직접 호출 후보

LangChain tool은 LLM이 필요할 때 호출할 수 있게 해주는 interface에 가깝다.

현재 `persistence.py`, `safety_layer.py`, `final_response.py`처럼 deterministic node가 항상 수행하는 저장은 tool wrapper를 거치지 않고 repository를 직접 호출하는 편이 더 단순하다.

전환 후보:

- `write_qa_ticket` -> `ticket_repository.save_qa_ticket`
- `write_answer_draft` -> `draft_repository.save_answer_draft`
- `write_evidence_docs` -> `draft_repository.save_evidence_docs`
- `write_safety_results` -> `safety_repository.save_safety_results`
- `write_final_response` -> `final_response_repository.save_final_response`
- `update_qa_ticket_status` -> `ticket_repository.update_qa_ticket_status`
- `write_failed_query` -> `failed_query_repository.save_failed_query`

### 2. Agent tool은 LLM이 선택해야 하는 read만 유지 후보

LLM이 상황에 따라 조회 여부를 판단해야 하는 read는 tool로 유지할 수 있다.

유지 후보:

- `read_gacha_logs`
- `read_item_delivery_logs`
- `collect_user_payment_context`

주의:

- `payment_agent.py`가 이미 `collect_payment_context_by_user()`를 직접 호출한다면 `collect_user_payment_context` tool 등록은 중복 조회를 만들 수 있다.
- node가 미리 context를 조회해서 state에 넣는 구조라면 LLM tool 등록은 제거하는 쪽이 더 안전하다.

### 3. FAQ/RAG vector search는 DB tool과 별도 계층으로 유지

FAQ 검색은 현재 `db_tools.py`에 등록된 DB tool이 아니라 `common.retrieval.vector_tools`를 직접 사용한다.

따라서 FAQ/RAG 정리는 DB tool 정리와 분리해서 보는 것이 좋다.

```text
DB tool cleanup: qa_ticket, draft, safety, final_response, logs
RAG cleanup: enrich, embed, vector search, rerank, evidence answer
```

## Recommended Direction

통합 단계 권장안:

1. `db_tools.py`는 LLM tool로 실제 필요한 read tool만 남긴다.
2. workflow node의 필수 저장 작업은 repository 직접 호출로 바꾼다.
3. write 계열은 tool이 아니라 repository/service 계층으로 정리한다.
4. payment/bug agent에서 DB 조회가 node 선조회인지 LLM tool 선택인지 하나로 통일한다.
5. FAQ/RAG는 `db_tools.py`에 억지로 넣지 말고 retrieval 전용 모듈로 관리한다.

## Open Questions


- chatbot runtime의 VOC성 문의 저장은 `qa_ticket`과 `final_response` 중심으로 정리되어 있으며,
  별도 VOC 전용 DB 저장 tool/repository 호출은 제거된 상태다.
- payment context 조회를 node 직접 조회로 고정할지, LLM tool 호출로 남길지
- bug context 조회도 payment처럼 node 직접 조회로 바꿀지
- insight 저장은 chatbot final_response 단계에서 제거했고, operation/CS automation 책임으로 유지한다.
