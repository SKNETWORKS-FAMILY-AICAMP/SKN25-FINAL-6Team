# Approval Agent Implementation Guide

`operation/approvalagent/`는 STEP2에서 생성된 `answer_draft`와 `evidence_docs`를 검토해 Approval Gate를 수행하는 디렉터리다.

이 디렉터리의 구현은 항상 아래 두 문서를 기준으로 맞춘다.

- `docs/ddl.md`

flowchart TB

DRAFT["RDBMS · answer_draft"]

EVIDENCE["RDBMS · evidence_docs"]

CHECK["답변 안전성 검사<br/><br/>
근거 문서 일치 여부<br/>
Hallucination 여부<br/>
정책 위반 여부<br/>
욕설 / 유해 표현 여부"]

SAFETY["RDBMS · safety_results<br/><br/>
hallucination_score<br/>
toxicity_score<br/>
policy_violation_score<br/>
factuality_score"]

RESULT{"승인 결과"}

HUMAN["운영자 검수<br/><br/>
답변 수정<br/>
수동 지급<br/>
환불 처리"]

EMAIL["긴급 알림 이메일 발송<br/><br/>
수신자: 운영 담당자 / 관리자<br/>
내용: ticket_id, risk_level, risk_reason, 문의 원문 요약"]

FINAL["최종 응답 게시<br/><br/>
QA_ticket.status = closed"]

DRAFT --> CHECK
EVIDENCE --> CHECK

CHECK --> SAFETY
SAFETY --> RESULT

RESULT -->|"바로 게시"| FINAL
RESULT -->|"사람수정 필요"| HUMAN
RESULT -->|"담당자 즉시 알림"| EMAIL

HUMAN --> FINAL

classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
classDef step fill:#f5f5f5,stroke:#888,color:#000;
classDef gate fill:#fff4cc,stroke:#c9a400,color:#000,stroke-width:2px;
classDef alert fill:#ffe8e8,stroke:#d64545,color:#000,stroke-width:2px;

class DRAFT,EVIDENCE,SAFETY db;
class CHECK,HUMAN,FINAL step;
class RESULT gate;
class EMAIL alert;
```


즉 코드 안의 payload, 판단 단계, 테이블 필드명, 상태 전이는 이 두 문서에 없는 임의 구조로 만들지 않는다.

## 기준 문서 해석

`docs/ddl.md` 기준으로 Approval Gate가 직접 읽거나 만들어야 하는 핵심 데이터는 아래다.

- 입력:
  - `QA_ticket`
  - `ticket_analysis`
  - `answer_draft`
  - `evidence_docs`
  - `payments`
  - `refunds`
  - `item_delivery_logs`
- 출력:
  - `safety_results`
  - Approval 판단 결과에 해당하는 파생 payload

`docs/operation_dashboard.md`의 Approval Gate 머메이드 기준 단계는 아래다.

1. `answer_draft`와 `evidence_docs` 입력
2. 근거 일치 여부, hallucination, policy risk, harmful 표현 여부 점검
3. `safety_results` 생성
4. `approved`, `human_review`, `urgent_alert` 중 하나 결정
5. 필요 시 human-in-the-loop로 운영자 검토 후 최종 처리

즉 이 디렉터리의 책임은 "답변 작성"이 아니라 "답변 승인 판단"이다.

## 입력 payload 기준

현재 구현의 기본 입력 payload는 아래 형태를 전제로 한다.

- `qa_ticket`
- `account_context`
- `operation_logs`
- `ticket_analysis`
- `answer_draft`
- `evidence_docs`

seed 기준 기본값은 `data.seed_payload.SEED_APPROVAL_INPUT_PAYLOAD`를 사용한다.

`account_context`는 DDL 테이블명이 아니라 `community_users`와 `game_accounts`를 병합한 파생 입력이다. 다만 Approval Gate는 이 필드를 직접 조작하기보다 검토 맥락용으로만 읽는다.

## 출력 payload 기준

Approval Gate 이후 최소 산출물은 아래다.

- `safety_results`
- `approval_result`
- `human_review_request` 또는 `final_outcome`

seed 기준 목표 형태는 `data.seed_payload.SEED_APPROVAL_OUTPUT_PAYLOAD`다.

## `chain.py` 구현 로직

`chain.py`는 Approval Gate의 판단 단위를 단계 함수와 LCEL chain으로 나눈 실행 계층이다. 여기서는 규칙 하드코딩보다 "LLM에게 판단을 시키되, 출력 포맷은 Pydantic으로 고정"하는 방향을 쓴다.

### 공통 원칙

- `docs/ddl.md`에 있는 필드명 기준으로 payload를 읽는다.
- `docs/operation_dashboard.md`의 Approval Gate 순서를 벗어나지 않는다.
- 각 단계 함수는 하나의 판단 책임만 가진다.
- 반환 형식은 Pydantic schema로 고정한다.
- 입력 payload가 없으면 `SEED_APPROVAL_INPUT_PAYLOAD`를 사용한다.

### 내부 구성

`chain.py`는 아래 계층으로 나뉘는 것이 맞다.

1. payload 로더
2. structured output schema
3. 모델 호출 헬퍼
4. Approval 단계별 함수
5. LCEL chain 조합

### 필요한 schema

최소 아래 schema가 필요하다.

- `EvidenceAlignmentResult`
- `SafetyScoreResult`
- `ApprovalDecisionResult`
- `HumanReviewRequestResult`
- `UrgentAlertPayloadResult`
- `FinalOutcomeResult`
- `ApprovalPayload` (전체 입력 payload 래퍼)

각 schema는 DDL 또는 Approval Gate 단계와 연결되어야 한다.

- `SafetyScoreResult`는 `safety_results` 테이블 필드와 최대한 맞춘다.
- `ApprovalDecisionResult`는 `approved`, `human_review`, `urgent_alert` 세 값만 허용한다.
- `HumanReviewRequestResult`, `FinalOutcomeResult`는 후속 runner나 dashboard가 읽기 쉬운 파생 객체다.

### 모델 호출 방식

- 모델은 `settings.openai_model` 기준으로 초기화한다.
- `init_chat_model(settings.openai_model)`로 모델 객체를 만든다.
- 각 LLM 단계는 `with_structured_output(schema)`를 써서 출력 형식을 강제한다.
- 각 단계는 payload JSON 전체를 넘기고, schema에 맞는 결과만 받는다.

즉 `chain.py`의 핵심은 "판단은 LLM, 형식은 Pydantic, 순서는 LCEL"이다.

### 단계별 책임

#### `load_approval_payload`

- 목적: 입력 payload를 정규화한다.
- 역할:
  - 외부 payload가 있으면 clone해서 사용
  - 없으면 `SEED_APPROVAL_INPUT_PAYLOAD` 사용
- 이 단계는 판단 로직이 아니라 진입점 정리용이다.

#### `check_evidence_alignment`

- 목적: `answer_draft.draft_text`가 `evidence_docs.evidence_text` 범위 안에 있는지 심사한다.
- 입력:
  - `answer_draft`
  - `evidence_docs`
  - 필요 시 `ticket_analysis`
- 출력:
  - `supported_claims`
  - `unsupported_claims`
  - `risk_notes`
  - `needs_human_review`

이 단계는 Approval Gate 머메이드의 `CHECK` 단계 중 "근거 문서 일치 여부"를 담당한다.

#### `score_safety_result`

- 목적: DDL의 `safety_results` 형태에 맞는 구조를 만든다.
- 입력:
  - `qa_ticket`
  - `ticket_analysis`
  - `answer_draft`
  - `evidence_docs`
  - `operation_logs`
- 출력:
  - `safety_id`
  - `draft_id`
  - `hallucination_score`
  - `toxicity_score`
  - `policy_violation_score`
  - `factuality_score`
  - `checked_at`

이 단계는 머메이드의 `SAFETY` 단계에 대응한다.

#### `decide_approval_result`

- 목적: safety 결과와 운영 로그를 종합해 최종 승인 경로를 정한다.
- 입력:
  - `ticket_analysis`
  - `answer_draft`
  - `evidence_docs`
  - `operation_logs`
  - 필요 시 `check_evidence_alignment` 결과
  - 필요 시 `score_safety_result` 결과
- 출력:
  - `approval_result`
  - `review_reason`
  - `recommended_action`
  - `priority`

판단 기준은 문서상 다음을 반영해야 한다.

- `approved`: 근거와 초안이 일치하고 safety risk가 낮은 경우
- `human_review`: 확신이 낮거나 운영자 확인이 필요한 경우
- `urgent_alert`: 결제/환불/지급 등 고위험 이슈로 즉시 운영자 개입이 필요한 경우

특히 `payments.success`와 `item_delivery_logs.fail` 조합은 보수적으로 다뤄야 한다.

#### `build_human_review_request`

- 목적: human-in-the-loop 단계로 넘길 검토 요청 payload 생성
- 입력:
  - `approval_result`
  - `review_reason`
  - `recommended_action`
  - `priority`
  - `qa_ticket`
  - `answer_draft`
- 출력:
  - `ticket_id`
  - `draft_id`
  - `review_reason`
  - `recommended_action`
  - `priority`
  - `requested_at`

이 객체는 DDL 테이블이 아니라 운영 검토용 파생 payload다.

#### `build_final_outcome`

- 목적: Approval Gate 종료 시점의 최종 결과 payload 생성
- 입력:
  - `approval_result`
  - `qa_ticket`
  - `answer_draft`
  - 필요 시 human review 결과
- 출력:
  - `ticket_id`
  - `status`
  - `approval_result`
  - `operator_action`

이 결과는 후속 단계나 dashboard가 읽기 쉬운 최종 요약 객체다.

#### `approval_core_chain`, `approval_review_chain`, `approval_chain`

- 목적: Approval Gate 전체를 LCEL sequence로 실행
- 역할:
  - payload 로드
  - 근거 정렬 판단
  - safety scoring
  - approval decision
  - 필요 시 human review request 생성
  - final outcome 생성

단, 현재 구현에서 human review 입력은 `chain.py` 안이 아니라 `runners/run_approval.py`에서 처리한다.

## `prompts.py` 구현 로직

`prompts.py`는 Approval Agent가 어떤 역할로 판단할지 고정하는 계층이다. 여기서는 답변 생성 프롬프트가 아니라 "심사자 프롬프트"를 작성해야 한다.

### 기본 역할 정의

프롬프트는 아래를 강하게 고정해야 한다.

- 너는 CS 답변 생성기가 아니라 Approval Gate reviewer다.
- 초안을 다시 쓰지 말고 승인 가능 여부만 판단한다.
- `evidence_docs`에 없는 사실을 추가로 상상하지 않는다.
- 결제, 환불, 지급 실패는 보수적으로 판단한다.
- 출력은 반드시 구조화된 형식만 반환한다.

### 프롬프트 분리 기준

`prompts.py`에는 최소 아래 수준의 프롬프트 구분이 필요하다.

- 공통 system prompt
- evidence alignment prompt
- safety scoring prompt
- approval decision prompt
- human review request prompt
- final outcome prompt

지금처럼 단계 함수 내부 문자열로 유지할 수도 있지만, 유지보수를 위해 `prompts.py`로 분리하는 방향이 더 낫다.

### 프롬프트에 반드시 들어가야 하는 맥락

- `qa_ticket.title`
- `qa_ticket.raw_content`
- `ticket_analysis.category`
- `ticket_analysis.risk_level`
- `ticket_analysis.routing_target`
- `answer_draft.draft_text`
- `evidence_docs`
- 필요 시 `operation_logs.payments`
- 필요 시 `operation_logs.refunds`
- 필요 시 `operation_logs.item_delivery_logs`

`gacha_logs`는 결제/지급 이슈보다 우선순위가 낮지만, 카테고리가 가챠일 때는 참고 맥락으로 넣는다.

## `run_approval.py` 실행 로직

현재 Approval Gate의 실제 실행 계층은 `runners/run_approval.py`다.

이 runner의 책임은 아래다.

- seed 또는 외부 payload 로드
- `CHECK -> SAFETY -> DECISION -> HUMAN/FINAL` 순서를 코드로 고정
- 필요 시 사람 입력을 터미널에서 받기
- 최종 payload 출력

즉 현재 구조는 LangChain agent orchestration이 아니라, "LLM을 단계별로 호출하는 순차 runner"에 가깝다.

### 현재 기준 실행 순서

`runners/run_approval.py`는 아래 순서로 함수 호출을 고정하는 것이 맞다.

1. `load_approval_payload`
2. `check_evidence_alignment`
3. `score_safety_result`
4. `decide_approval_result`
5. 필요 시 `build_human_review_request`
6. `build_final_outcome`

이 순서는 `docs/operation_dashboard.md`의 Approval Gate 머메이드 순서를 그대로 코드로 고정한 것이다.

### Human review 처리 위치

현재 human review 입력은 `chain.py` 안에서 받지 않고 `runners/run_approval.py`에서 받는다.

- `chain.py`: Approval 단계 계산과 LCEL sequence
- `runners/run_approval.py`: `approve / reject / edit` 입력 처리

### 승인 입력 형식

현재 runner에서 사람 입력은 아래 형식이다.

- `operator_action`: `answer_edit`, `manual_payout`, `refund_process`, `urgent_response`, `approve_as_is` 중 하나 (기본값: `approve_as_is`)
- `review_note`: 검토 메모 (자유 텍스트)
- `edited_answer_draft`: `operator_action == "answer_edit"`일 때만 입력받는 수정된 초안 텍스트

현재 기준에서 운영자가 검토하는 대상은 함수 args가 아니라 생성된 아래 결과다.

- `human_review_request`
- `final_outcome`

## 현재 구현 상태와 잔여 리스크

`chain.py`와 `runners/run_approval.py` 구현이 완료된 상태다. `approval_core_chain`(LCEL)이 `load → alignment → safety → decision` 순서를 강제하고, human review 입력은 runner에서 처리한다.

다만 아래 구조적 리스크는 여전히 유효하다.

1. `build_human_review_request`, `build_final_outcome`는 선행 단계 산출물(`approval_decision`)이 payload에 있다고 가정한다. 순서를 지키지 않고 단독 호출하면 runtime 오류가 발생할 수 있다.
2. `approval_chain`을 우회해 단계 함수를 직접 호출하면 단계 일관성이 깨진다. 항상 `approval_core_chain` 또는 `approval_chain`을 통해 실행해야 한다.

## 구현 순서

이 디렉터리 구현 순서는 아래가 맞다.

1. `docs/ddl.md`와 `docs/operation_dashboard.md` 기준으로 입력/출력 필드 고정
2. `chain.py`의 Pydantic schema와 단계 책임 고정
3. `prompts.py`에 심사형 프롬프트 분리
4. `runners/run_approval.py`에서 순차 실행 흐름 고정
5. runner에서 `operator_action` 입력 처리 (`answer_edit`, `manual_payout`, `refund_process`, `urgent_response`, `approve_as_is`)

즉 문서 없는 임의 구현보다, DDL과 머메이드 단계에 맞는 책임 분리부터 먼저 고정해야 한다.

## 구현 시 금지 사항

- DDL에 없는 필드명을 임의로 핵심 판단 기준으로 추가하지 않는다.
- `chain.py` 안에서 직접 `input()`으로 사람 입력을 받지 않는다.
- approval 판단과 초안 재작성 로직을 섞지 않는다.
- `approval_result` 값을 자유 문자열로 만들지 않는다.
- `safety_results` 필드를 DDL과 다르게 축약하거나 이름을 바꾸지 않는다.
- 실행 순서를 LLM 자율 판단에 맡기지 않는다.
- human review가 필요한데도 결과 검토 없이 최종 결과를 바로 확정하지 않는다.

## 관련 파일

- 상위 운영 개요: `operation/README.md`
- STEP1/2 문서: `operation/step12agent/README.md`
- 데이터 스키마: `docs/ddl.md`
- 플로우 기준: `docs/operation_dashboard.md`
- seed payload: `data/seed_payload.py`
- 구현 파일:
  - `operation/approvalagent/chain.py`
  - `operation/approvalagent/prompts.py`
  - `runners/run_approval.py`
