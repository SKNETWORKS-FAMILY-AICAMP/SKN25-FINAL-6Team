# Chatbot Agents

이 폴더는 LangGraph 전환을 위한 category별 node 구현을 담습니다.

현재 프로젝트의 메인 실행 경로는 `chatbot/graph/workflow.py`의 LangGraph workflow입니다. 이 폴더의 category node들은 공통 `create_agent` reasoning unit을 호출해 `answer_draft`를 만들고, 이후 safety/final response node로 넘깁니다.

## 전체 역할

```text
orchestrator_node
  -> category / routing_target 결정
  -> write_qa_ticket
  -> write_ticket_analysis

category agent node
  -> invoke_chatbot_agent(state)
  -> answer_draft 생성
  -> draft/evidence baseline persistence
```

## 파일별 책임

| 파일 | 노드 함수 | 책임 |
|------|-----------|------|
| `orchestrator.py` | `orchestrator_node` | 문의 정규화, category/routing_target 결정, 티켓 및 분석 저장 |
| `payment_agent.py` | `payment_agent_node` | 결제/환불/아이템 지급 로그 조회, 결제 문의 답변 초안 생성 |
| `bug_agent.py` | `bug_agent_node` | 가챠/아이템 지급 로그 조회, 인게임 버그 문의 답변 초안 생성 |
| `faq_agent.py` | `faq_agent_node` | FAQ cache 조회/저장, 일반 FAQ 답변 초안 생성 |
| `voc_agent.py` | `voc_agent_node` | LLM 기반 VOC 유형 분류 및 유형별 접수형 답변 초안 생성 |

## State 입력

모든 node는 `ChatbotState`를 입력으로 받습니다.

주요 필드:

```text
ticket_id
user_id
session_id
account_id
source_type
raw_content
cleaned_content
category
routing_target
draft_id
answer_draft
safety_passed
retry_count
```

## Orchestrator

`orchestrator_node`는 현재 LLM 없이 keyword 기반 baseline으로 동작합니다.

현재 분류 규칙:

```text
결제 / 환불 / 미지급 / 아이템 포함
  -> category = 결제
  -> routing_target = urgent_alert

버그 / 오류 / 튕김 / 끼임 포함
  -> category = 인게임버그
  -> routing_target = rag_reply

건의 / 불만 / 칭찬 / 의견 포함
  -> category = VOC
  -> routing_target = rag_reply

그 외
  -> category = FAQ
  -> routing_target = rag_reply
```

호출 tools:

```text
write_qa_ticket
write_ticket_analysis
```

향후 개선:

```text
- LLM classifier 연결
- Query Enrichment 추가
- routing_target을 keyword가 아니라 정책 기반으로 세분화
- urgent_alert일 때 Operator Dashboard로 보내는 분기 추가
```

## Payment Agent

`payment_agent_node`는 결제 문의 처리 baseline입니다.

호출 tools:

```text
read_payments
read_refunds
read_item_delivery_logs
write_answer_draft
write_evidence_docs
```

현재 동작:

```text
1. account_id로 payments 조회
2. account_id로 item_delivery_logs 조회
3. 첫 payment_id로 refunds 조회
4. 지급 실패 로그가 있으면 운영자 검토 필요 문구 포함
5. answer_draft와 evidence_docs 저장
```

향후 개선:

```text
- 결제 성공/실패/환불 상태별 답변 분기
- delivery_status별 미지급 판단 고도화
- urgent_alert일 때 Operator Dashboard 큐 적재
```

## Bug Agent

`bug_agent_node`는 인게임 버그 문의 처리 baseline입니다.

호출 tools:

```text
read_gacha_logs
read_item_delivery_logs
write_answer_draft
write_evidence_docs
```

현재 동작:

```text
1. account_id로 gacha_logs 조회
2. account_id로 item_delivery_logs 조회
3. 재현 조건 또는 지급 여부 확인 필요 문구 생성
4. answer_draft와 evidence_docs 저장
```

향후 개선:

```text
- 자체 버그 / 미지급 의심 버그 분리
- 미지급 의심 시 payment_agent 경로로 연결
- 복잡 버그는 GitHub issue 또는 Operator Dashboard로 연결
```

## FAQ Agent

`faq_agent_node`는 FAQ 문의 처리 baseline입니다.

호출 tools:

```text
get_cache
set_cache
write_answer_draft
write_evidence_docs
```

현재 동작:

```text
1. cleaned_content 기준 query_hash 생성
2. cache hit이면 cache 답변 사용
3. cache miss이면 baseline FAQ 답변 생성 후 cache 저장
4. answer_draft와 evidence_docs 저장
```

현재는 ChromaDB나 embedding search를 직접 호출하지 않습니다. RAG 품질 검증 단계에서 `embed_query`, `search_documents`, `rerank_documents`를 연결할 예정입니다.

현재 3번 Workflow/LangGraph/Safety 담당 범위에서는 FAQ가 graph 안에서 정상 라우팅되고, cache hit/miss, draft 저장, evidence 저장, safety_layer까지 흐르는지만 확인합니다. 실제 RAG 검색 품질, ChromaDB 연결, seed embedding 검증은 Tools/Data/RAG 담당 범위에서 완료한 뒤 이 node에 연결합니다.

향후 개선:

```text
- cache miss일 때 vector search 연결
- 검색 결과가 없을 때 failed_queries 저장
- FAQ 답변 가능/불가 판단 추가
```

## VOC Agent

`voc_agent_node`는 VOC 접수형 baseline입니다. VOC 세부 유형/감정/요약은 LLM으로 먼저 분류하고, LLM 호출이 실패하면 keyword fallback을 사용합니다.

호출 tools:

```text
write_voc_feedback
write_answer_draft
write_evidence_docs
```

현재 동작:

```text
1. LLM으로 VOC 유형/감정/요약 분류
2. VOC_DB 성격의 저장소에 VOC 내용 저장
3. VOC 유형별 접수형 답변 생성
4. answer_draft 저장
5. VOC 접수 evidence 저장
```

응답 문구는 LLM 자유 생성이 아니라 VOC 유형별 deterministic template입니다. workflow에서도 VOC는 `safety_layer`를 거치지 않고 `final_response`로 바로 이동합니다. VOC는 실패 케이스가 아니라 정상적인 고객 의견 접수이므로 `failed_query`에는 저장하지 않습니다.

## 개발 규칙

```text
- 기존 chatbot/agent.py create_agent 실행 경로를 깨지 않는다.
- 각 node는 ChatbotState를 받아 dict를 반환한다.
- tools 호출은 seed/mock mode에서 동작해야 한다.
- VOC 세부 유형 분류에는 외부 LLM 호출을 사용하되, 실패 시 keyword fallback을 유지한다.
- 파일별 책임을 넘는 큰 분기는 graph/workflow.py에서 처리한다.
```
