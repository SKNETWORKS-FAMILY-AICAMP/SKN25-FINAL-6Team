# agents/ — 카테고리별 Agent 노드

각 파일은 LangGraph 노드 함수 하나를 export한다. 함수 시그니처는 `(state: ChatbotState) -> dict`.

| 파일 | 노드 함수 | 역할 |
|------|-----------|------|
| `orchestrator.py` | `orchestrator_node` | Toxic Filter → LLM 분류 → category/routing_target 결정 |
| `payment_agent.py` | `payment_agent_node` | 결제·환불·지급 로그 조회 후 답변 초안 작성 |
| `bug_agent.py` | `bug_agent_node` | 지급 로그·가챠 로그 분석 후 버그 답변 작성 |
| `faq_agent.py` | `faq_agent_node` | 캐시 확인 → RAG 검색 → 문서 기반 답변 작성 |
| `voc_agent.py` | `voc_agent_node` | 고객 의견 수용 + 피드백 접수 안내 |

## 노드 반환 규약

모든 Agent 노드는 아래 키를 반환한다:

```python
{
    "answer_draft": str,   # 생성된 답변 텍스트
    "draft_id": int,       # write_answer_draft 반환값
    "retry_count": 0,      # Safety 재시도 카운터 초기화
}
```

## Orchestrator 분류 규칙

- Toxic 키워드 감지 시 → `category="VOC"`, `routing_target="urgent_alert"` (LLM 호출 없이)
- `결제` 분류 시 → `routing_target="urgent_alert"`
- 나머지 → `routing_target="rag_reply"`
