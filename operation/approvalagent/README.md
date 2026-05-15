# Approval Agent

`approvalagent/`는 STEP2에서 생성한 답변 초안을 검토하고, 자동 승인 가능 여부 또는 운영자 검토 필요 여부를 판단하는 Approval Gate 전용 디렉터리다.

## 역할

`docs/operation_dashboard.md`의 Approval Gate 흐름을 기준으로 아래 단계를 담당한다.

1. `answer_draft` 검토
2. `evidence_docs`와 초안의 근거 일치 여부 확인
3. hallucination, toxicity, policy violation, factuality 판단
4. `safety_results` 생성
5. `approval_result`를 `approved`, `human_review`, `urgent_alert` 중 하나로 결정
6. 필요 시 `human_review_request` 또는 `final_outcome` 생성

이 디렉터리의 목표는 "답변 생성"이 아니라 "답변 승인 가능 여부 판단"이다.

## 입력 payload

Approval Gate의 기본 입력은 아래다.

- `qa_ticket`
- `account_context`
- `operation_logs`
- `ticket_analysis`
- `answer_draft`
- `evidence_docs`

현재 seed 기준으로는 `data.seed_payload.SEED_APPROVAL_INPUT_PAYLOAD`를 사용한다.

## 출력 payload

Approval Gate는 최소 아래 결과를 만든다.

- `safety_results`
- `approval_result`
- `human_review_request` 또는 `final_outcome`

현재 seed 기준 목표 형태는 `data.seed_payload.SEED_APPROVAL_OUTPUT_PAYLOAD`다.

## 현재 코드 기준 구현 방식

현재 [agent.py](/abs/path/C:/SKN25-FINAL-6Team/operation/approvalagent/agent.py:1)는 `create_agent(settings.openai_model, tools=tools, system_prompt=...)` 형태의 베이스라인 에이전트다.

현재 [tools.py](/abs/path/C:/SKN25-FINAL-6Team/operation/approvalagent/tools.py:1)는 규칙 기반 if/else가 아니라, LLM에게 판단을 맡기고 Pydantic schema로 출력을 고정하는 구조다.

핵심 포인트:

- `init_chat_model(settings.openai_model)`로 모델 생성
- `with_structured_output(...)`로 schema 고정
- approval 단계별 판단을 각각 tool로 분리
- 기본 입력이 없으면 `SEED_APPROVAL_INPUT_PAYLOAD` 사용

즉 현재 구현은 "LLM 심사 + structured output" 기준으로 정리되어 있다.

## Tool 구성 기준

현재 tool 책임은 아래처럼 나뉜다.

### 1. `load_approval_payload`

- 목적: approval 입력 payload를 로드하거나 seed payload를 기본값으로 반환

### 2. `check_evidence_alignment`

- 목적: `answer_draft`가 `evidence_docs` 범위 안에서 작성되었는지 판단
- 출력: `supported_claims`, `unsupported_claims`, `risk_notes`, `needs_human_review`

### 3. `score_safety_result`

- 목적: 초안의 안전성 점수를 구조화된 형태로 생성
- 출력 필드:
  - `safety_id`
  - `draft_id`
  - `hallucination_score`
  - `toxicity_score`
  - `policy_violation_score`
  - `factuality_score`
  - `checked_at`

### 4. `decide_approval_result`

- 목적: 근거 일치 여부, safety 판단, 운영 로그를 종합해 `approved`, `human_review`, `urgent_alert` 중 하나를 결정
- 출력: `approval_result`, `review_reason`, `recommended_action`, `priority`

### 5. `build_human_review_request`

- 목적: `human_review` 또는 `urgent_alert` 케이스에서 운영자 검토 요청 payload 생성

### 6. `build_final_outcome`

- 목적: Approval Gate 결과를 후속 단계가 읽기 쉬운 최종 outcome 형태로 정리

### 7. `run_approval_gate`

- 목적: Approval Gate 전체를 한 번에 실행해 구조화된 최종 결과 반환

## Prompt 기준

`prompts.py`와 각 tool 내부 system prompt는 생성형 CS 응답이 아니라 심사형 판단 프롬프트를 전제로 한다.

지켜야 할 원칙:

1. 기존 `answer_draft`를 다시 쓰지 않는다.
2. `evidence_docs`에 없는 사실을 추가 추정하지 않는다.
3. 승인 판단과 수정 제안을 구분한다.
4. 반드시 구조화된 출력만 반환한다.

프롬프트에 들어가야 하는 핵심 입력:

- `qa_ticket.title`
- `qa_ticket.raw_content`
- `ticket_analysis.category`
- `ticket_analysis.risk_level`
- `ticket_analysis.routing_target`
- `answer_draft.draft_text`
- `evidence_docs`
- 필요 시 `operation_logs.payments`, `refunds`, `item_delivery_logs`

## Human-in-the-loop 기준

현재 문서 기준의 1차 구현 방향은 `HumanInTheLoopMiddleware`다.

- 이유: Approval Gate 이후의 운영 액션은 승인 단위로 멈추고 확인하기 쉽기 때문이다.
- 우선 차단할 대상:
  - `build_human_review_request`
  - `build_final_outcome`
  - 추후 추가될 운영 액션 tool

향후 승인 UX가 더 복잡해져서 tool 호출 단위보다 그래프 상태 단위 제어가 필요해지면 LangGraph `interrupt`로 확장한다.

즉 현재 기준은:

- 기본값: `HumanInTheLoopMiddleware`
- 확장안: LangGraph `interrupt`

## 추가 권장 middleware

- `Model retry`: safety scoring, approval decision 모델 호출 재시도
- `Model fallback`: 주 모델 장애 시 대체 모델 사용
- `PII detection`: human review 요청과 최종 결과에 민감 정보 과다 노출 방지
- `Model call limit`: Approval Gate의 불필요한 반복 호출 방지

## 현재 구현 상태

- `agent.py`: `create_agent(...)` 베이스라인 존재
- `tools.py`: LLM + Pydantic structured output 기반 tool 존재
- `prompts.py`: Approval Gate 시스템 프롬프트 존재
- middleware 연결: 아직 미구현

즉 Approval Gate의 최소 실행 뼈대와 판단 도구는 있지만, 운영 환경용 middleware와 후속 액션 연결은 아직 남아 있다.

## 작성 계획

Approval Gate를 현재 베이스라인에서 실제 human-in-the-loop 동작까지 확장할 때의 권장 순서는 아래다.

### 1. `agent.py`에 middleware 부착

- `HumanInTheLoopMiddleware`는 tool이 아니라 agent 실행 계층에 붙인다.
- 따라서 `create_agent(...)` 호출부에서 middleware를 추가한다.
- 1차 대상 tool:
  - `build_human_review_request`
  - `build_final_outcome`
- 추후 운영 액션 tool이 추가되면 같은 middleware 대상에 포함한다.

### 2. interrupt 대상 tool 이름 고정

- middleware는 특정 tool 호출을 가로채므로, 어떤 tool을 멈출지 먼저 고정해야 한다.
- Approval Gate 기준 1차 승인 포인트는 "운영자 검토 요청 생성"과 "최종 결과 확정"이다.
- 따라서 tool 이름과 책임을 먼저 안정화한 뒤 middleware 설정을 붙인다.

### 3. 승인 입력 형식 정의

- `HumanInTheLoopMiddleware`의 기본 승인 단위는 `approve`, `edit`, `reject`다.
- Approval Agent에서는 최소 아래 형식을 전제로 한다.

```json
{"decision": "approve"}
```

```json
{"decision": "reject"}
```

```json
{
  "decision": "edit",
  "args": {
    "payload": {}
  }
}
```

- `approve`: 기존 tool args 그대로 실행
- `reject`: 해당 tool 호출 중단
- `edit`: 사람이 수정한 args로 다시 실행

### 4. runner 또는 호출 계층에서 사람 입력 처리

- `tools.py` 안에서 `input()`으로 직접 받는 구조로 가지 않는다.
- agent 실행 결과가 HITL 상태로 멈추면, runner 또는 상위 호출 계층에서 승인 입력을 받아 재개한다.
- 초기 버전은 터미널 입력으로 시작할 수 있고, 이후 웹 UI나 운영 콘솔로 확장할 수 있다.

### 5. Approval 결과와 HITL 포인트 연결

- `run_approval_gate` 또는 단계별 tool 호출 결과가 `human_review`, `urgent_alert`면 후속 tool 호출 전에 멈추게 한다.
- 예:
  - `decide_approval_result`가 `approved`면 `build_final_outcome` 전 승인
  - `decide_approval_result`가 `human_review`, `urgent_alert`면 `build_human_review_request` 전 승인

### 6. 이후 middleware 확장

- 운영 환경으로 갈수록 아래를 추가한다.
  - `Model retry`
  - `Model fallback`
  - `PII detection`
  - `Model call limit`

즉 작성 순서는 "tool 작성"보다 "agent에 middleware 부착", "승인 대상 tool 고정", "사람 입력을 받을 runner 정의"가 먼저다.

## 관련 문서

- 상위 운영 개요: `operation/README.md`
- STEP1/2 문서: `operation/step12agent/README.md`
- 전체 플로우: `docs/operation_dashboard.md`
- 데이터 스키마: `docs/ddl.md`
- seed payload: `data/seed_payload.py`
