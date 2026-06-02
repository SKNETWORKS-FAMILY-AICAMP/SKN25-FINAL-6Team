# Chatbot FAQ/RAG Cleanup Notes

## Scope

This note is for analysis only. It does not change the chatbot runtime.

Analysis scope:

- FAQ/RAG 중복 확인
- production RAG 경로 확인
- `chains/faq_rag.py`와 `generation/faq_agent.py` 역할 비교
- 이후 통합 단계에서 정리할 후보 기록

## Current Production Path

현재 챗봇 workflow에서 FAQ 카테고리가 선택되면 다음 흐름으로 실행된다.

```text
workflow
-> route_by_category(category="faq")
-> faq_agent_node
-> run_faq_rag
-> enrich_retrieval_query
-> embed_query.invoke
-> search_document_chunks
-> rerank_documents.invoke
-> _generate_evidence_answer
-> draft_persistence
-> safety_layer
-> final_response
```

즉 production FAQ/RAG의 실제 실행 중심은 `apps/chatbot/backend/generation/faq_agent.py`의 `run_faq_rag()`이다.

## `generation/faq_agent.py`

역할:

- LangGraph의 FAQ node인 `faq_agent_node()`를 제공한다.
- `run_faq_rag()`에서 검색과 답변 생성을 모두 처리한다.
- low evidence, relevance gate, failed query 저장까지 담당한다.
- LLM 답변 생성 `_generate_evidence_answer()`도 이 파일 안에 있다.

현재 RAG 단계:

```text
_active_query
-> enrich_retrieval_query
-> embed_query.invoke
-> search_document_chunks(prefer_faq=True)
-> rerank_documents.invoke
-> _is_low_evidence
-> _passes_relevance_gate
-> _generate_evidence_answer
```

현재 특징:

- `FAQ_POLICY.tools`는 빈 리스트다.
- FAQ agent는 LLM tool-calling 방식으로 vector search tool을 호출하지 않는다.
- RAG는 agent tool이 아니라 deterministic function pipeline으로 직접 실행된다.
- 실패 쿼리만 `write_failed_query` tool을 통해 저장한다.

## `chains/faq_rag.py`

역할:

- `retrieve_faq_context(raw_query)`로 FAQ 검색 context만 반환한다.
- `format_contexts(documents)`로 RAGAS/eval 친화적인 context 문자열을 만든다.
- `faq_ragas_eval.py`에서 `retrieve_faq_context()`를 사용한다.

현재 RAG 단계:

```text
enrich_retrieval_query
-> embed_query.invoke
-> search_document_chunks(prefer_faq=True)
-> rerank_documents.invoke
-> FaqRagContext 반환
```

현재 특징:

- production workflow에 직접 연결되어 있지 않다.
- 답변 생성, low evidence 처리, failed query 저장은 하지 않는다.
- 검색 trace를 남기는 구조라 평가/디버깅에는 적합하다.

## Duplication

중복되는 부분:

- `enrich_retrieval_query`
- `embed_query.invoke`
- `search_document_chunks(prefer_faq=True)`
- `rerank_documents.invoke`
- `FAQ_RERANK_CANDIDATE_TOP_K` 기반 candidate top k 계산

차이가 있는 부분:

| 항목 | `generation/faq_agent.py` | `chains/faq_rag.py` |
| --- | --- | --- |
| production 연결 | 연결됨 | 직접 연결 안 됨 |
| 답변 생성 | 있음 | 없음 |
| low evidence 판단 | 있음 | 없음 |
| relevance gate | 있음 | 없음 |
| failed query 저장 | 있음 | 없음 |
| retrieval trace | 간단 출력 중심 | 명시적 trace 반환 |
| eval 사용성 | 낮음 | 높음 |

## Recommended Cleanup Direction

통합 단계에서 권장하는 정리 방향:

1. 검색 전용 함수는 `chains/faq_rag.py` 또는 별도 retrieval service로 단일화한다.
2. `generation/faq_agent.py`는 FAQ node orchestration과 답변 생성만 담당하게 한다.
3. `run_faq_rag()` 내부의 검색 단계는 `retrieve_faq_context()`를 호출하도록 바꾼다.
4. low evidence, relevance gate, failed query 저장은 production policy이므로 `faq_agent.py`에 남기거나 별도 guard 함수로 분리한다.
5. eval은 같은 retrieval function을 사용하게 해서 production/eval 검색 결과가 갈라지지 않도록 한다.

권장 구조:

```text
faq_agent_node
-> run_faq_rag
   -> retrieve_faq_context
      -> enrich/embed/search/rerank
   -> evidence/relevance guard
   -> generate answer
```

## Open Questions

- Redis/cache를 FAQ retrieval 앞단에 붙일지 여부
- cache key 기준을 `retrieval_query`로 할지, `raw_query + enrichment`로 할지
- failed query 저장은 tool 호출로 유지할지 repository 직접 호출로 바꿀지
- `chains/faq_rag.py`를 production shared module로 승격할지, `retrieval/` 하위 service로 이동할지
