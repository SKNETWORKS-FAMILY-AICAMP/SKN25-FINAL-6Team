# Chatbot

게임 CS 고객 문의를 접수하고, 문의 유형을 분류한 뒤 필요한 근거를 조회해 답변 초안을 생성하는 챗봇 데모 베이스라인입니다.

현재 챗봇의 메인 실행 경로는 LangGraph `StateGraph` 기반 workflow입니다. Category별 node는 공통 `create_agent` reasoning unit을 호출하고, Graph가 routing, safety, final response 흐름을 제어합니다.

## Architecture Direction

현재 베이스라인은 `StateGraph`가 전체 workflow를 제어하고, `create_agent`는 category node 안에서 reasoning과 답변 초안 생성을 담당합니다.

현재 baseline 단계에서는 category별 prompt/tool policy를 분리해 policy-specific `create_agent` reasoning unit을 실행합니다.
향후 LangGraph workflow 내부에서 직접 tool 호출 node로 점진 전환할 수 있습니다.
`PaymentAgentInput`, `SafetyInput`, `SafetyDecision`은 현재 runtime 필수 입력이 아니라 future graph-ready contract입니다.

역할 분리는 다음 기준을 따릅니다.

```text
Graph = orchestration / workflow
Agent = reasoning / answer drafting
```

향후 LangGraph가 담당할 영역:

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

`create_agent`가 담당할 영역:

```text
FAQ 응답 생성
결제 문의 reasoning
VOC 이해
버그 설명
고객-facing 답변 초안 생성
```

현재 `chatbot.agent`는 legacy singleton을 유지하지 않고, category policy가 넘긴 prompt/tools로 `create_agent`를 생성합니다.

## 역할

- 고객 문의 접수
- 문의 카테고리 및 라우팅 대상 판단
- 결제/환불/지급/가챠 로그 조회
- FAQ/정책 문서 검색
- 답변 초안 생성
- 티켓 분석, 답변, 근거, safety 결과 저장

## 폴더 구조

```text
chatbot/
├── agent.py
├── schemas.py
├── constants.py
├── generation/prompts/
├── chains/
├── generation/
├── retrieval/
├── repository/
├── tools/
├── safety/
├── generation/response/
├── memory/
├── notifications/
├── observability/
└── utils/
```

## 주요 파일

| 파일 | 설명 |
|------|------|
| `agent.py` | LangChain `create_agent` 기반 메인 챗봇 agent |
| `schemas.py` | 챗봇 state 스키마와 카테고리/라우팅 타입 정의 |
| `constants.py` | 카테고리, 라우팅, safety threshold 상수 |
| `tools/db_tools.py` | DB 조회/저장 tool |
| `tools/vector_tools.py` | Chroma 기반 문서 embedding/search/rerank tool |
| `retrieval/cache_tools.py` | FAQ 답변 캐시 tool |
| `tools/registry.py` | `create_agent`에 주입되는 tool 목록 |
| `generation/prompts/system_prompt.py` | 챗봇 시스템 프롬프트 |
| `chains/workflow.py` | LangGraph `StateGraph` 정의 |
| `chains/routing.py` | category/safety 기반 routing 함수 |
| `runners/run_chatbot.py` | 단일 턴 실행 함수와 간단 멀티턴 데모 헬퍼 |

## Baseline Flow

```text
Access/Input
  -> Orchestration
  -> Intelligence
  -> Draft/Evidence Persistence
  -> Safety
  -> Final Response
```

### 1. Access/Input Layer

사용자 입력과 세션 정보를 `ChatbotState`로 받습니다. 실제 화면, 로그인, 권한 관리는 이 모듈의 책임이 아니며 상위 인터페이스에서 처리한다고 가정합니다.

주요 state 필드:

```text
user_id
session_id
account_id
source_type
raw_query
enriched_query
conversation_summary
turn_count
```

### 2. Orchestration Layer

문의 내용을 정리하고, 문의 유형과 라우팅 대상을 결정합니다.

분류 값:

```text
category: 결제 / 인게임버그 / FAQ / VOC
routing_target: rag_reply / urgent_alert
```

기본 규칙:

```text
rag_reply: 단순 FAQ, 일반 안내, 단순 게임 플레이 문의, 낮은 위험의 VOC
urgent_alert: 결제 분쟁, 환불, 유료 아이템 미지급, 복잡 버그, 정책 민감 이슈, 운영자 검토 필요 케이스
```

관련 tools:

```text
write_qa_ticket
write_ticket_analysis
```

### 3. Intelligence Layer

분류된 category에 맞는 tools를 사용해 근거를 조회하고 답변을 생성합니다.

```text
결제:
  read_payments
  read_refunds
  read_item_delivery_logs

인게임버그:
  read_gacha_logs
  read_item_delivery_logs

FAQ:
  get_cache
  embed_query
  search_documents
  rerank_documents
  set_cache

VOC:
  LLM으로 VOC 유형/감정/요약 분류
  VOC 유형별 접수형 응답 생성
```

### 4. Draft And Evidence Persistence

생성된 답변과 근거를 저장합니다. 현재는 `USE_SEED_PAYLOAD=true`일 때 실제 DB 저장 대신 mock 응답을 반환합니다.

관련 tools:

```text
write_answer_draft
write_evidence_docs
```

### 5. Safety Layer

최종 응답 전 아래 항목을 점검하는 것을 baseline 정책으로 둡니다.

```text
hallucination / factuality
toxicity / hate / violence / harassment
PII 포함 여부
```

관련 tool:

```text
write_safety_results
```

현재 safety는 LangGraph의 `safety_layer` 노드에서 처리합니다. `AUTO_RESPONSE`, `MASKING`, `SAFE_FALLBACK`, `BLOCK_RESPONSE`, `REVIEW_QUEUE` 같은 분기 값은 `final_response_node`가 최종 사용자 응답으로 변환합니다.

## State

`schemas.py`의 `ChatbotState`는 agent 실행 중 필요한 상태값을 정의합니다.

| 필드 | 설명 |
|------|------|
| `messages` | LangChain 대화 메시지 |
| `user_id` | 사용자 ID |
| `session_id` | 현재 챗봇 세션 ID |
| `account_id` | 게임 계정 ID |
| `source_type` | 유입 채널 |
| `raw_query` | 사용자 문의 원문 |
| `enriched_query` | 정규화된 문의 내용 |
| `ticket_id` | QA 티켓 ID |
| `category` | 문의 카테고리 |
| `routing_target` | `rag_reply` 또는 `urgent_alert` |
| `draft_id` | 답변 초안 ID |
| `draft_text` | 답변 초안 |
| `safety_passed` | safety 통과 여부 |
| `safety_action` | safety 이후 workflow action |
| `safety_reason` | safety 판단 사유 |
| `review_required` | 운영자 검토 필요 여부 |
| `retry_count` | 재시도 횟수 |
| `conversation_summary` | 이전 턴 요약, 필요 시 상위 레이어에서 주입 |
| `turn_count` | 현재 세션의 사용자 발화 순번 |

현재 state 자체는 영구 저장하지 않습니다. DB에 남길 데이터는 tool을 통해 별도로 저장합니다.

## State Example

```python
from chatbot.agent import invoke_payment_agent

result = invoke_payment_agent({
    "messages": [
        {
            "role": "user",
            "content": "결제했는데 아이템이 안 들어왔어요.",
        }
    ],
    "ticket_id": 1001,
    "user_id": "user_001",
    "session_id": "session_001",
    "account_id": 101,
    "source_type": "chatbot",
    "raw_query": "결제했는데 아이템이 안 들어왔어요.",
    "enriched_query": "결제했는데 아이템이 안 들어왔어요.",
})

print(result["messages"][-1].content)
```

## 저장 정책

현재 `USE_SEED_PAYLOAD=true`이면 `db_tools.py`의 write tool은 실제 DB 저장 대신 mock 응답을 반환합니다.

실제 DB 연동 시 저장 대상은 다음과 같습니다.

| 대상 | 내용 |
|------|------|
| `QA_ticket` | 문의 원문 및 Q/A 누적 기록 |
| `ticket_analysis` | 카테고리 및 라우팅 결과 |
| `answer_draft` | 생성된 답변 초안 |
| `evidence_docs` | 답변에 사용된 근거 문서/로그 |
| `safety_results` | safety 평가 결과 |

향후 실제 DB 접근 코드는 공통 DB access layer로 분리합니다.

## 실행 방법

프로젝트 루트에서 실행합니다.

```bash
python3 runners/run_chatbot.py
```

Windows PowerShell에서는 아래처럼 실행할 수 있습니다.

```powershell
python runners\run_chatbot.py
```

또는 Python 코드에서 직접 `chatbot.agent.invoke_payment_agent`,
`chatbot.agent.invoke_faq_agent`, `chatbot.agent.invoke_bug_agent`를 import해
카테고리별 agent를 호출할 수 있습니다.

### Python 실행 예시

`runners.run_chatbot.run`은 단일 턴 실행을 위한 얇은 wrapper입니다.

```python
from runners.run_chatbot import run

answer = run(
    ticket_id=1001,
    user_message="결제했는데 아이템이 안 들어왔어요.",
    account_id=101,
)
print(answer)
```

멀티턴 흐름을 확인할 때는 이전 `messages`를 다음 호출에 넘기는 방식으로 설계합니다. 현재 runner에는 smoke 확인용 `run_multiturn_demo`가 있습니다.

```python
from runners.run_chatbot import run_multiturn_demo

answers = run_multiturn_demo()
for answer in answers:
    print(answer)
```

## 간단 멀티턴 테스트 설계

목표는 실제 DB 저장 검증이 아니라, 같은 세션 안에서 이전 발화를 참고하되 현재 티켓 metadata를 유지하는지 확인하는 것입니다.

| 케이스 | 1턴 | 2턴 | 기대 결과 |
|------|------|------|------|
| 결제 미지급 후속 질문 | 결제했는데 아이템이 안 들어옴 | 방금 건 환불 가능 여부 질문 | 2턴에서 이전 결제 건을 문맥으로 이해하고 결제/환불 검토 안내 |
| FAQ 후속 질문 | 쿠폰 등록 방법 질문 | 안드로이드도 같은지 질문 | 2턴에서 쿠폰 등록 맥락을 유지하고 FAQ성 답변 |
| VOC 후속 의견 | 업데이트가 불편하다는 의견 | 이 내용 전달됐는지 확인 | LLM 분류 결과를 유지하고 접수형 응답에서 과장된 처리 완료 표현 금지 |

검증 포인트:

```text
- result["messages"]에 이전 턴과 현재 턴이 함께 남는가
- ticket_id, user_id, session_id, account_id가 현재 state 기준으로 유지되는가
- 최종 답변이 내부 tool 이름, routing_target, score를 노출하지 않는가
- 결제/환불/미지급처럼 위험도가 있는 문의는 운영자 검토 가능성을 보수적으로 안내하는가
```

## 환경 변수

`.env.sample`을 참고합니다.

```text
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=openai:text-embedding-3-small
RETRIEVAL_TOP_K=3
USE_SEED_PAYLOAD=true
DATABASE_URL=postgresql://...
```

`USE_SEED_PAYLOAD=true`이면 `data/seed_payload.py`의 seed 데이터를 사용하고, DB write tools는 실제 저장 대신 mock 결과를 반환합니다.

## 현재 한계

```text
- LangGraph 기반 layer별 node 분리는 아직 적용하지 않았습니다.
- 실제 DB access layer는 아직 구현 전입니다.
- USE_SEED_PAYLOAD=false이면 DB-backed tool은 NotImplementedError를 발생시킵니다.
- Operator Dashboard 적재는 실제 화면 연동 전 단계입니다.
- Safety Layer는 별도 decision graph가 아니라 agent prompt 정책으로 표현합니다.
- FAQ cache는 in-memory 방식이라 프로세스 재시작 시 초기화됩니다.
- 멀티턴 장기 요약은 아직 자동 생성하지 않으며, 필요 시 `conversation_summary`에 상위 레이어가 주입합니다.
```

## Next Step

데모 베이스라인 이후에는 아래 순서로 확장할 수 있습니다.

```text
1. Orchestration, Intelligence, Safety를 LangGraph node로 분리
2. routing_target 기반 urgent_alert 처리 경로 추가
3. SafetyAction 기반 conditional branching 구현
4. Operator Dashboard 연동
5. 실제 DB access layer 연결
```
