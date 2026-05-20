# Chatbot 모듈 개요

게임 CS 고객 응대 챗봇이다. 현재 메인 실행 경로는 LangGraph `StateGraph`
workflow이며, category node 안에서 LangChain `create_agent` 기반 reasoning unit을
호출한다.

## 실행 흐름

```text
runners/run_chatbot.py
  -> chatbot.chains.workflow.graph
  -> orchestrator/category/safety/final_response nodes
  -> category node에서 invoke_payment_agent / invoke_faq_agent / invoke_bug_agent
  -> db/vector/cache tools
```

`chatbot.agent`는 payment/faq/bug policy가 넘긴 prompt/tools로 category별
`create_agent`를 생성한다. 내부 공통 실행 함수는 private helper로만 두고,
외부 호출 인터페이스는 `invoke_payment_agent`, `invoke_faq_agent`,
`invoke_bug_agent` 세 가지로 제한한다.

현재 baseline 단계에서는 category별 prompt/tool policy를 분리해 `create_agent` 기반 reasoning unit을 실행한다.
향후 LangGraph workflow 내부에서 직접 tool 호출 node로 점진 전환할 수 있다.
`PaymentAgentInput`, `SafetyInput`, `SafetyDecision`은 현재 runtime 필수
입력이 아니라 future graph-ready contract다.

## 역할 분리

```text
Graph = orchestration / workflow
Agent = reasoning / answer drafting
```

향후 StateGraph가 담당할 영역:

```text
routing
threshold 판단
retry
cache check
DB write
safety branching
HITL / review queue
observability
```

create_agent가 담당할 영역:

```text
FAQ 응답 생성
결제 문의 reasoning
VOC 이해
버그 설명
고객-facing 답변 초안 생성
```

## 주요 파일

| 경로 | 역할 |
|------|------|
| `agent.py` | `create_agent` baseline, graph-ready agent interface |
| `schemas.py` | `ChatbotState`와 Pydantic 입출력 계약 |
| `tools/` | DB, Vector, Cache tool |
| `generation/` | 향후 세부 agent/node 구현 위치 |
| `chains/` | 향후 StateGraph workflow 구현 위치 |
| `runners/run_chatbot.py` | 단일 턴 wrapper와 멀티턴 smoke helper |

## 실행 예시

```python
from chatbot.agent import invoke_payment_agent

result = invoke_payment_agent({
    "messages": [
        {
            "role": "user",
            "content": "ticket_id=1001\naccount_id=101\n\nCustomer inquiry:\n결제했는데 아이템이 안 들어왔어요",
        }
    ],
    "ticket_id": 1001,
    "account_id": 101,
    "raw_query": "결제했는데 아이템이 안 들어왔어요",
    "enriched_query": "결제했는데 아이템이 안 들어왔어요",
})
```

CLI 실행은 `python runners/run_chatbot.py`를 사용한다.

멀티턴 smoke 확인은 `runners.run_chatbot.run_multiturn_demo()`를 사용한다. 이전
`messages`를 다음 호출 state에 넘겨 같은 세션 문맥을 유지하되, `ticket_id`,
`account_id`, `raw_query`는 현재 턴 기준으로 둔다.

## 저장 정책

현재 `db_tools.py`는 `USE_SEED_PAYLOAD=true`일 때 실제 DB 저장 대신 mock 응답을
반환한다. 실제 DB 저장은 이후 공통 DB access layer로 분리한다.
