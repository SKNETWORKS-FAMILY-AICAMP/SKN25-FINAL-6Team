# Chatbot Tools

챗봇 agent가 외부 데이터에 접근하거나 처리 결과를 저장할 때 사용하는 LangChain tool 모음입니다.

모든 tool은 `@tool(parse_docstring=True)` 형태로 정의되어 있으며, `create_agent`의 tools 목록에 등록됩니다.

## 공통 응답 포맷

모든 tool은 JSON string을 반환합니다.

Read tool은 아래 포맷을 사용합니다.

```json
{
  "status": "ok",
  "data": [],
  "count": 0
}
```

Write tool은 처리 결과와 생성/대상 ID를 포함한 `status: ok` 응답을 반환합니다.

```json
{
  "status": "ok",
  "ticket_id": 1001
}
```

## 파일 구성

```text
tools/
├─ db_tools.py
├─ vector_tools.py
├─ cache_tools.py
└─ registry.py
```

## db_tools.py

RDB 기반 조회/저장 역할을 담당합니다.

현재는 `USE_SEED_PAYLOAD=true`일 때 `data/seed_payload.py`의 seed 데이터를 사용합니다. 실제 DB 구현은 아직 없으며, `USE_SEED_PAYLOAD=false`이면 `NotImplementedError`가 발생합니다.

### Read Tools

| Tool | 설명 |
|------|------|
| `read_payments(account_id)` | 계정의 결제 내역 조회 |
| `read_refunds(payment_id)` | 결제 건의 환불 기록 조회 |
| `read_item_delivery_logs(account_id)` | 계정의 아이템 지급 로그 조회 |
| `read_gacha_logs(account_id)` | 계정의 가챠 로그 조회 |

### Write Tools

| Tool | 설명 |
|------|------|
| `write_qa_ticket(payload)` | QA 티켓 저장 |
| `write_ticket_analysis(payload)` | 문의 분석 결과 저장 |
| `write_answer_draft(payload)` | 답변 초안 저장 및 `draft_id` 반환 |
| `write_evidence_docs(payload)` | 답변 근거 문서/로그 저장 |
| `write_safety_results(payload)` | safety 평가 결과 저장 |
| `append_qa_ticket_message(payload)` | `QA_ticket.raw_content`에 Q/A 메시지 누적 |
| `write_failed_query(payload)` | FAQ 검색 실패 또는 근거 부족 query 저장 |
| `write_voc_feedback(payload)` | VOC 유형, 감정, 원문, 요약을 VOC_DB 성격의 저장소에 적재 |

VOC는 정상적인 고객 의견 접수 흐름입니다. VOC 유형별 접수형 응답은 `answer_draft`에 저장하고 `QA_ticket.raw_content`에 append하지만, `failed_query`에는 저장하지 않습니다.
현재 baseline에서는 VOC 세부 유형/감정/요약 분류에 LLM을 사용하고, 고객 응답 문구는 유형별 deterministic template을 사용하므로 LLM safety 검사를 생략할 수 있습니다.

## vector_tools.py

FAQ, 정책, 공지 문서 검색을 위한 vector/RAG tool입니다.

| Tool | 설명 |
|------|------|
| `embed_query(text)` | 사용자 질의를 embedding vector로 변환 |
| `search_documents(embedding_json, top_k)` | seed 문서 chunk와 cosine similarity 검색 |
| `rerank_documents(docs_json, query)` | 검색 결과 재정렬, 현재는 pass-through |

현재 검색 대상은 `data/seed_payload.py`의 문서 chunk와 embedding입니다. seed embedding이 비어 있으면 검색 결과가 나오지 않을 수 있습니다.

`embed_query(text)`는 OpenAI embedding API를 호출합니다. 테스트에서는 외부 API 호출을 피하기 위해 seed embedding을 직접 사용해 `search_documents`를 검증합니다.

## cache_tools.py

FAQ성 응답 재사용을 위한 인메모리 TTL 캐시입니다.

| Tool | 설명 |
|------|------|
| `get_cache(query_hash)` | query hash 기준 캐시 조회 |
| `set_cache(query_hash, answer, ttl)` | 답변 캐시 저장 |

현재 캐시는 Python 프로세스 메모리에만 저장됩니다. 서버가 재시작되면 캐시는 사라집니다. 운영 환경에서는 Redis 같은 외부 캐시로 교체하는 것이 좋습니다.

## Seed Payload

`data/seed_payload.py`는 tool 테스트와 baseline 실행을 위한 seed 데이터를 제공합니다.

| Seed | 설명 |
|------|------|
| `SEED_CHAT_SCENARIOS` | 챗봇에 새로 입력할 테스트 문의 시나리오 |
| `SEED_OPERATION_LOGS` | 결제, 환불, 아이템 지급, 가챠 로그 |
| `SEED_DOCUMENTS` | FAQ, 정책, 공지 원문 |
| `SEED_DOCUMENT_CHUNKS` | RAG 검색용 문서 chunk |
| `SEED_DOCUMENT_EMBEDDINGS` | seed vector 검색용 embedding |

현재 baseline 시나리오는 아래 케이스를 포함합니다.

| Scenario | 설명 |
|----------|------|
| `payment_missing_delivery` | 결제 성공 + 아이템 지급 실패 |
| `faq_event_reward_delay` | 이벤트 보상 지급 FAQ |
| `gacha_delivery_success` | 가챠 로그 존재 + 아이템 정상 지급 |
| `gacha_delivery_missing` | 가챠 로그 존재 + 아이템 지급 실패 |
| `voc_event_complaint` | 이벤트 보상 불만 VOC |

## Tests

tools baseline 테스트는 아래 명령으로 실행합니다.

```bash
PYTHONPATH=. pytest -q tests/chatbot/test_cache_tools.py
PYTHONPATH=. pytest -q tests/chatbot/test_vector_tools.py
```

전체 tools 관련 테스트를 한 번에 실행하려면:

```bash
PYTHONPATH=. pytest -q tests/chatbot
```

## 향후 변경 방향

- `db_tools.py`의 실제 SQL 구현은 공통 DB access layer로 이동
- `vector_tools.py`는 실제 vector DB 연동으로 교체
- `cache_tools.py`는 Redis 기반 cache로 교체 가능
- tool 함수는 agent가 호출하는 얇은 wrapper 역할만 유지
