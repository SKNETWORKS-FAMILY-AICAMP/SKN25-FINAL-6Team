# Chatbot Tools

챗봇 agent가 외부 데이터에 접근하거나 처리 결과를 저장할 때 사용하는 LangChain tool 모음입니다.

모든 tool은 `@tool(parse_docstring=True)` 형태로 정의되어 있으며, `create_agent`의 tools 목록에 등록됩니다.

## 파일 구성

```text
tools/
├─ db_tools.py
├─ vector_tools.py
├─ cache_tools.py
└─ README.md
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

## vector_tools.py

FAQ, 정책, 공지 문서 검색을 위한 vector/RAG tool입니다.

| Tool | 설명 |
|------|------|
| `embed_query(text)` | 사용자 질의를 embedding vector로 변환 |
| `search_documents(embedding_json, top_k)` | seed 문서 chunk와 cosine similarity 검색 |
| `rerank_documents(docs_json, query)` | 검색 결과 재정렬, 현재는 pass-through |

현재 검색 대상은 `data/seed_payload.py`의 문서 chunk와 embedding입니다. seed embedding이 비어 있으면 검색 결과가 나오지 않을 수 있습니다.

## cache_tools.py

FAQ성 응답 재사용을 위한 인메모리 TTL 캐시입니다.

| Tool | 설명 |
|------|------|
| `get_cache(query_hash)` | query hash 기준 캐시 조회 |
| `set_cache(query_hash, answer, ttl)` | 답변 캐시 저장 |

현재 캐시는 Python 프로세스 메모리에만 저장됩니다. 서버가 재시작되면 캐시는 사라집니다. 운영 환경에서는 Redis 같은 외부 캐시로 교체하는 것이 좋습니다.

## 향후 변경 방향

- `db_tools.py`의 실제 SQL 구현은 공통 DB access layer로 이동
- `vector_tools.py`는 실제 vector DB 연동으로 교체
- `cache_tools.py`는 Redis 기반 cache로 교체 가능
- tool 함수는 agent가 호출하는 얇은 wrapper 역할만 유지
