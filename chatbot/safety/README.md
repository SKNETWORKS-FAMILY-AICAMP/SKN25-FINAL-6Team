# Chatbot Safety Layer

이 폴더는 LangGraph 전환용 safety node를 담습니다.

현재 safety는 완성된 정책 엔진이 아니라 baseline keyword check입니다. 목적은 category agent가 생성한 `answer_draft`를 받은 뒤 `safety_passed`, `retry_count`, `write_safety_results` 흐름을 먼저 연결하는 것입니다.

## 현재 파일

| 파일 | 노드 함수 | 역할 |
|------|-----------|------|
| `safety_layer.py` | `safety_layer_node` | 답변 초안 safety 검사 및 결과 저장 |
| `__init__.py` | - | safety package marker |

## 현재 입력

`safety_layer_node`는 `ChatbotState`를 입력으로 받습니다.

주요 필드:

```text
ticket_id
draft_id
answer_draft
retry_count
```

## 현재 출력

```python
{
    "safety_passed": bool,
    "final_decision": "AUTO_RESPONSE | BLOCK_RESPONSE",
    "retry_count": int,
}
```

## 현재 검사 방식

현재는 아래 keyword가 `answer_draft`에 포함되면 unsafe로 판단합니다.

```text
욕설
혐오
폭력
```

unsafe로 판단하면:

```text
safety_passed = False
retry_count += 1
```

safe로 판단하면:

```text
safety_passed = True
retry_count 유지
```

## 저장 흐름

검사 결과는 `write_safety_results` tool로 저장합니다.

현재 baseline payload:

```text
draft_id
ticket_id
decision_type
factuality
hallucination
toxicity
reason
```

`USE_SEED_PAYLOAD=true`일 때는 실제 DB 저장 대신 mock 응답을 반환합니다.

## 저장 책임 정리

팀 논의 기준으로 저장 책임은 아래처럼 나눕니다.

```text
failed_queries
  -> FAQ/RAG에서 답변 근거를 찾지 못한 질문만 저장
  -> Safety Layer의 BLOCK/REVIEW/FALLBACK 결과는 저장하지 않음

safety_results
  -> Safety Layer의 검사 점수와 decision_type 저장
  -> AUTO_RESPONSE / MASKING / SAFE_FALLBACK / BLOCK_RESPONSE / REVIEW_QUEUE 같은 분기 결과 기록

QA_ticket.raw_content
  -> 사용자에게 최종으로 나간 Q/A 대화 내용 누적
  -> AUTO_RESPONSE뿐 아니라 BLOCK_RESPONSE, SAFE_FALLBACK, REVIEW_QUEUE 안내용 고정 답변도 최종 응답이면 저장 대상
```

즉, Safety Layer는 답변 본문을 영구 저장하는 책임이 아니라, 어떤 안전성 판단으로 어떤 후속 경로가 선택되었는지를 `safety_results.decision_type`에 남기는 책임을 가집니다. 실제 사용자-facing 답변 생성은 `chatbot/response/final_response.py`에서 처리하고, 향후 DB 연동 시 Final Response 단계에서 `QA_ticket.raw_content`에 append하는 방향으로 둡니다.

## 향후 Safety Decision

최종 아키텍처에서는 단순 `safety_passed`보다 아래 decision 기반 분기가 필요합니다.

```text
AUTO_RESPONSE
  -> 최종 답변 승인

MASKING
  -> 개인정보 마스킹 후 재검사

SAFE_FALLBACK
  -> 근거 부족 또는 애매한 답변
  -> 고정 안내문 또는 재생성 요청

BLOCK_RESPONSE
  -> 높은 toxicity / hate / violence
  -> 응답 차단 메시지

REVIEW_QUEUE
  -> 정책 위반 / 고위험 / 반복 실패
  -> Operator Dashboard로 전달
  -> 사용자에게는 접수/검토 안내용 고정 답변 반환
```

## 권장 확장 순서

```text
1. safety_passed bool 유지한 상태에서 final_decision 필드 추가
2. PII Detection / Response Validation / Moderation 점수 필드 추가
3. MASKING 후 재검사 경로 구현
4. SAFE_FALLBACK retry feedback 구현
5. REVIEW_QUEUE를 Operator Dashboard 큐로 연결
6. Final Response 단계에서 고정 답변을 QA_ticket.raw_content에 append
```

## 주의사항

```text
- safety_layer는 category agent의 답변 초안을 검증하는 역할만 담당한다.
- category 분류나 tool 조회는 agents 폴더에서 처리한다.
- routing은 graph/workflow.py에서 처리한다.
- 현재 create_agent 메인 실행 경로에는 이 safety_layer가 직접 연결되어 있지 않다.
```
