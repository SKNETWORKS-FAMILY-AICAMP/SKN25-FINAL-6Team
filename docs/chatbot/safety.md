# Chatbot Safety Layer

현재 Safety Layer는 payment/bug/faq node가 생성한 `draft_text`를 검사하고, 결과를
`write_safety_results`로 저장한 뒤 다음 분기를 결정하는 노드입니다.

## 현재 구현

`safety_layer_node`는 다음 순서로 동작합니다.

```text
draft_text 입력
→ OpenAI Moderation API 검사
→ safety_action 결정
→ safety_results 저장
→ state에 safety 결과 반환
```

Moderation API 호출은 아래 모델을 사용합니다.

```python
client.moderations.create(
    model="omni-moderation-latest",
    input=text,
)
```

현재 구현은 OpenAI Moderation API가 정상 동작한다는 전제로 작성되어 있습니다.

## 입력

```text
ticket_id
draft_id
draft_text
retry_count
```

## 출력

```python
{
    "safety_passed": bool,
    "safety_action": "AUTO_RESPONSE | BLOCK_RESPONSE",
    "safety_reason": str,
    "review_required": bool,
    "retry_count": int,
}
```

## 저장 Payload

`write_safety_results`에는 다음 값을 저장합니다.

```text
draft_id
ticket_id
safety_action
factuality_score
hallucination_score
toxicity_score
policy_violation_score
safety_reason
```

현재 moderation은 toxicity, hate, violence, harassment 계열 점수를 중심으로
`toxicity_score`와 `policy_violation_score`를 계산합니다. `factuality_score`와
`hallucination_score`는 아직 별도 검증 모델이 없으므로 baseline 고정값입니다.

## Safety Action

현재 실제 구현은 아래 두 action을 사용합니다.

```text
AUTO_RESPONSE
BLOCK_RESPONSE
```

설계상 확장 가능한 action은 다음과 같습니다.

```text
MASKING
SAFE_FALLBACK
REVIEW_QUEUE
```

## 향후 개선

```text
1. PII Detection 추가
2. Response Validation 모델 추가
3. factuality / hallucination 실제 평가 구현
4. MASKING / SAFE_FALLBACK / REVIEW_QUEUE 분기 구현
5. REVIEW_QUEUE 발생 시 Slack notification 연동
```
