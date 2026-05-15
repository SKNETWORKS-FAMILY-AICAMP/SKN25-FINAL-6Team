# Chatbot 모듈 개요

게임 CS 고객 응대 챗봇이다. 현재 메인 실행 경로는 LangGraph 수동
`StateGraph`가 아니라 LangChain `create_agent` 기반이다.

## 실행 흐름

```text
runners/run_chatbot.py
  -> chatbot.agent.agent
  -> create_agent(...)
  -> db/vector/cache tools
```

## 주요 파일

| 경로 | 역할 |
|------|------|
| `agent.py` | `create_agent` 기반 메인 챗봇 agent |
| `schemas.py` | `AgentState` 확장 `ChatbotState` |
| `tools/` | DB, Vector, Cache tool |
| `agents/` | 기존 StateGraph 노드 구현체 |
| `graph/workflow.py` | 기존 StateGraph 워크플로우, 현재 runner 기본 경로 아님 |

## 실행 예시

```python
from chatbot.agent import agent

result = agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": "ticket_id=1001\naccount_id=101\n\nCustomer inquiry:\n결제했는데 아이템이 안 들어왔어요.",
        }
    ],
    "ticket_id": 1001,
    "account_id": 101,
    "raw_content": "결제했는데 아이템이 안 들어왔어요.",
    "cleaned_content": "결제했는데 아이템이 안 들어왔어요.",
})
```

CLI 실행은 `python runners/run_chatbot.py`를 사용한다.

## 저장 정책

현재 `db_tools.py`는 `USE_SEED_PAYLOAD=true`일 때 실제 DB 저장 대신 mock
응답을 반환한다. 실제 DB 저장은 이후 공통 DB access layer로 분리한다.
