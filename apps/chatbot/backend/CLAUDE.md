# Chatbot 모듈 개요

게임 CS 고객 응대 챗봇이다. 현재 메인 실행 경로는 FastAPI `/chat`에서
`chatbot.service.chatbot_service`를 거쳐 LangGraph `StateGraph` workflow를
호출하는 구조다. 결제/버그는 LangChain `create_agent` 기반 reasoning unit을
사용하고, FAQ는 별도 RAG 흐름을 사용한다.

## 실행 흐름

```text
api.main:/chat
  -> chatbot.service.chatbot_service.run_chatbot
  -> chatbot.chains.workflow.graph
  -> ticket_preprocess -> payment/faq/bug/voc node
  -> draft_persistence -> safety_layer 또는 ticket_completion
  -> ticket_completion
```

`chatbot.agent`는 payment/bug policy가 넘긴 prompt/tools로 category별
`create_agent`를 생성한다. FAQ는 `generation/faq_agent.py`에서 검색,
근거 구성, 답변 생성을 직접 수행한다.

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
HITL / review required
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
| `service/chatbot_service.py` | FastAPI에서 호출하는 단일 턴/스트리밍 workflow wrapper |

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
    "normalized_query": "결제했는데 아이템이 안 들어왔어요",
})
```

로컬 실행은 FastAPI 앱을 띄워 `/chat` API로 확인한다. 이전
`messages`와 `conversation_summary`는 `chatbot_service`에서 state에 주입해
같은 세션 문맥을 유지하되, `ticket_id`,
`account_id`, `raw_query`는 현재 턴 기준으로 둔다.

## 저장 정책

`db_tools.py`는 `src.common.db.connection.db_connection()`을 사용하는 repository
계층을 통해 실제 PostgreSQL을 조회/저장한다. DB 연결이나 SQL 오류가 발생하면
repository의 `safe_read` / `safe_write`가 에러 payload와 운영 로그를 남긴다.
