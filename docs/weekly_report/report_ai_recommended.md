# AI 권장 액션과 행별 해석

## 구현 위치

| 경로 | 역할 |
| --- | --- |
| `apps/weekly_report/ai/actions.py` | 주간 권장 액션 생성 |
| `apps/weekly_report/ai/row_interpret.py` | 검토용 행별 해석 생성 |

## 1. 주간 권장 액션

### 호출 위치

`apps/weekly_report/report.py`

`report.run()`은 아래 입력을 만들어 `generate_ai_actions(ai_input)`에 전달한다.

```python
ai_input = {
    "summary": {
        "total_count": len(current_rows),
        "prev_total": len(previous_rows),
    },
    "spike_alerts": alerts,
    "top5_improvements": requests,
    "category_distribution": distribution(current_rows, "category"),
}
```

### 출력 형식

```python
{
    "headline": "...",
    "actions": [
        {
            "rank": 1,
            "category": "...",
            "action": "...",
            "reason": "...",
        }
    ],
}
```

### 현재 프롬프트 규칙

- 제공된 데이터만 사용
- 다음 주 실행 가능한 액션 제안
- 3~5개 액션 제안
- 최소 1개 마케팅/프로모션 제안 포함
- 근거 없는 추론 금지

### fallback

아래 경우 fallback 응답을 반환한다.

- `LLM_MODEL` 또는 `LLM_API_KEY` 미설정
- 구조화 LLM 호출 실패

fallback headline:

- `AI recommended actions could not be generated.`

## 2. 검토용 행별 해석

### 호출 위치

`apps/weekly_report/build/payload.py`

`pick_review_rows(current_rows, limit=12)`로 고른 행에 대해 `generate_review_row_interpretations(review_rows)`를 호출한다.

### LLM 입력으로 보내는 행 정보

- `analysis_id`
- `ticket_id`
- `title`
- `status`
- `source_type`
- `category`
- `responder_type`
- `enriched_query`
- `risk_level`
- `sentiment`
- `routing_target`
- `pattern_risk_level`
- `analyzed_at`

### 출력 형식

```python
[
    {
        "analysis_id": 101,
        "ticket_id": 5001,
        "interpretation": "한 줄 한국어 해석",
    }
]
```

### fallback

행별 해석도 아래 경우 deterministic fallback 문장을 만든다.

- LLM 설정 없음
- LLM 호출 실패

fallback 문장은 각 행의 `title`, `category`, `risk_level`, `sentiment`, `routing_target`를 조합해 생성된다.

## 3. 리포트 payload 반영 위치

AI 결과는 최종적으로 아래 필드에 반영된다.

- `ai_interpretation`
- `narrative_insights`
- `column_insights`
- `report_sections`
- `review_rows[].ai_row_interpretation`

## 현재 구현에서 없는 것

현재 AI 모듈은 아래를 하지 않는다.

- SQL 직접 생성
- 별도 insight 테이블 적재
- 대시보드용 대화형 설명 API 제공
