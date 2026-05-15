# graph/ — LangGraph 워크플로우

## workflow.py

`StateGraph(ChatbotState)`를 조립하고 `graph = workflow.compile()`을 export한다.

## 노드 목록

| 노드 이름 | 연결 함수 |
|-----------|-----------|
| `orchestrator` | `orchestrator_node` |
| `payment_agent` | `payment_agent_node` |
| `bug_agent` | `bug_agent_node` |
| `faq_agent` | `faq_agent_node` |
| `voc_agent` | `voc_agent_node` |
| `safety_layer` | `safety_layer_node` |

## 엣지 구조

```
orchestrator
  ├─(결제)──────→ payment_agent ──→ safety_layer
  ├─(인게임버그)→ bug_agent     ──→ safety_layer
  ├─(FAQ)───────→ faq_agent     ──→ safety_layer
  └─(VOC)───────→ voc_agent     ──→ safety_layer

safety_layer
  ├─(통과 or 재시도 초과) → END
  └─(실패 + 재시도 가능)  → 해당 카테고리 Agent (최대 MAX_SAFETY_RETRY회)
```

## 라우팅 함수

| 함수 | 역할 |
|------|------|
| `_route_by_category` | `state["category"]` 값으로 Agent 선택 |
| `_route_after_safety` | `safety_passed` + `retry_count`로 종료/재시도 결정 |
