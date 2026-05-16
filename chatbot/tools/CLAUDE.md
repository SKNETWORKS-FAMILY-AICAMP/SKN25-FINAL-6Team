# tools/ — 도구 정의

모든 도구는 `@tool(parse_docstring=True)` 데코레이터를 사용한다.  
`USE_SEED_PAYLOAD=true`(기본값)이면 DB 없이 seed 데이터로 동작하고, `false`이면 `NotImplementedError`를 발생시켜 실제 DB 구현을 요구한다.

## db_tools.py — DB 읽기/쓰기

| 함수 | 설명 |
|------|------|
| `read_payments(account_id)` | 결제 내역 조회 |
| `read_refunds(payment_id)` | 환불 기록 조회 |
| `read_item_delivery_logs(account_id)` | 아이템 지급 로그 조회 |
| `read_gacha_logs(account_id)` | 가챠 로그 조회 |
| `write_qa_ticket(payload)` | QA 티켓 저장 |
| `write_ticket_analysis(payload)` | 티켓 분석 결과 저장 |
| `write_answer_draft(payload)` | 답변 초안 저장 → `draft_id` 반환 |
| `write_evidence_docs(payload)` | 근거 문서 참조 저장 |
| `write_safety_results(payload)` | Safety 평가 결과 저장 |
| `append_qa_ticket_message(payload)` | `QA_ticket.raw_content`에 Q/A 메시지 누적 |
| `write_failed_query(payload)` | FAQ 검색 실패 또는 근거 부족 query 저장 |
| `write_voc_feedback(payload)` | VOC 유형, 감정, 원문, 요약 저장 |

VOC는 정상적인 고객 의견 접수이므로 `failed_query`에 저장하지 않는다.  
현재 baseline의 VOC 응답은 완전 고정 문구이므로 LLM Safety 검사를 생략할 수 있다.

## vector_tools.py — 임베딩·검색

| 함수 | 설명 |
|------|------|
| `embed_query(text)` | OpenAI 임베딩 벡터 생성 |
| `search_documents(embedding_json, top_k)` | 코사인 유사도 검색 |
| `rerank_documents(docs_json, query)` | 재순위화 (현재 pass-through) |

seed 데이터의 `embedding_vector`가 비어 있으면 검색 결과가 없을 수 있다.  
`data/generate_seed_embeddings.py`를 먼저 실행해 벡터를 채운다.

## cache_tools.py — 인메모리 캐시

| 함수 | 설명 |
|------|------|
| `get_cache(query_hash)` | TTL 캐시 조회 |
| `set_cache(query_hash, answer, ttl)` | 캐시 저장 (기본 TTL 3600초) |

`query_hash`는 호출자(faq_agent)가 `hashlib.sha256`으로 생성한다.  
프로세스 재시작 시 캐시는 초기화된다. 영속성이 필요하면 Redis로 교체한다.
