# Chatbot 모듈 개요

게임 CS 자동화 챗봇. 고객 문의를 카테고리별로 분류하고 LangGraph 워크플로우로 처리한다.

## 전체 흐름

```
사용자 문의
    → orchestrator (Toxic Filter + LLM 분류)
    → [결제|인게임버그|FAQ|VOC] Agent
    → safety_layer (안전성 검사)
    → 통과 시 종료 / 실패 시 Agent 재시도 (최대 MAX_SAFETY_RETRY)
```

## 디렉터리 구조

| 경로 | 역할 |
|------|------|
| `schemas.py` | LangGraph 상태(`ChatbotState`) + Agent I/O 페이로드 정의 |
| `constants.py` | 임계값·카테고리 등 전역 상수 |
| `agents/` | 카테고리별 Agent 노드 함수 |
| `safety/` | Safety Layer 노드 함수 |
| `tools/` | DB·Vector·Cache 도구 |
| `graph/workflow.py` | StateGraph 조립 및 `graph` 인스턴스 |

## 주요 상수 (constants.py)

- `MAX_SAFETY_RETRY = 2` — Safety 실패 시 최대 재시도 횟수
- `FACTUALITY_THRESHOLD = 0.8` — 사실성 통과 기준
- `HALLUCINATION_THRESHOLD = 0.3` — 환각 통과 기준
- `TOXICITY_THRESHOLD = 0.7` — 독성 통과 기준

## 실행 방법

```python
from chatbot.graph.workflow import graph

result = graph.invoke({
    "messages": [],
    "ticket_id": 1001,
    "user_message": "결제는 완료됐는데 아이템이 안 왔어요",
    "account_id": 101,
    "category": "",
    "routing_target": "",
    "draft_id": None,
    "answer_draft": None,
    "safety_passed": None,
    "retry_count": 0,
})
print(result["answer_draft"])
```

## 시드 페이로드

`USE_SEED_PAYLOAD=true` (기본값)이면 DB 없이 `data/seed_payload.py` 데이터로 동작한다.
