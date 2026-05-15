# safety/ — Safety Layer

## 역할

Agent가 생성한 `answer_draft`를 LLM으로 평가해 안전성을 판정한다.

## 평가 지표

| 지표 | 방향 | 통과 기준 |
|------|------|-----------|
| `factuality` | 높을수록 좋음 | `>= 0.8` |
| `hallucination` | 낮을수록 좋음 | `<= 0.3` |
| `toxicity` | 낮을수록 좋음 | `<= 0.7` |

기준값은 `chatbot/constants.py`에서 관리한다.

## 노드 반환 규약

```python
{
    "safety_passed": bool,
    "retry_count": int,   # 실패 시 +1, 통과 시 유지
}
```

## 재시도 로직

`safety_passed=False`이고 `retry_count < MAX_SAFETY_RETRY`이면 `graph/workflow.py`의 conditional edge가 해당 카테고리 Agent로 되돌아간다.  
`MAX_SAFETY_RETRY` 초과 시에는 현재 draft를 그대로 종료한다.

## 평가 결과 저장

`write_safety_results` 도구로 draft_id별 점수를 기록한다.
