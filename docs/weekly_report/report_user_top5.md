# Top 5 개선 요청 산정 방식

## 구현 위치

- `apps/weekly_report/db/top_requests.py`

## 목적

주간 리포트에 들어갈 “개선 요청 Top 5”를 카테고리 단위로 계산한다.

현재 구현은 단순 건수 순위가 아니라 **건수 + 리스크 심각도**를 합친 점수로 정렬한다.

## 사용 데이터

| 테이블 | 용도 |
| --- | --- |
| `ticket_analysis` | 카테고리, 리스크 수준 |
| `qa_ticket` | 기간 필터 기준 |
| `voc_feedback` | 선택적 `topic_keywords` 보조 데이터 |

## 점수식

```text
priority_score = (count * 0.4) + (severity_score * 0.6)
```

`severity_score` 매핑:

- `critical` -> `4`
- `high` -> `3`
- `medium` -> `2`
- `low` -> `1`
- `unknown` -> `1`

## 처리 순서

1. 기간 내 `ticket_analysis.category`별 건수를 집계한다.
2. 같은 범위에서 카테고리별 최대 `risk_level`을 `severity_score`로 변환한다.
3. `priority_score`를 계산한다.
4. 점수 내림차순으로 정렬 후 상위 5개만 남긴다.
5. `level in {critical, high}`이면 `시급한 결함`, 그 외는 `편의 개선`으로 분류한다.

## `voc_feedback` 처리

`_fetch_category_keywords()`는 `voc_feedback.topic_keywords`를 읽어 카테고리별 상위 3개 키워드를 붙이려 한다.

주의:

- 라이브 DB 문서에는 `voc_feedback` 테이블이 없다.
- 구현은 이 조회가 실패하면 예외를 흡수하고 `topic_keywords=[]`로 계속 진행한다.
- 따라서 Top 5 계산 자체는 `voc_feedback` 없이도 동작한다.

## 반환 예시

```python
[
    {
        "rank": 1,
        "category": "payment",
        "count": 42,
        "severity_score": 4,
        "priority_score": 19.2,
        "level": "critical",
        "improvement_type": "시급한 결함",
        "topic_keywords": ["결제 실패", "환불", "중복 결제"],
    }
]
```

## 관련 함수

| 함수 | 역할 |
| --- | --- |
| `get_risk_level_score()` | 리스크 문자열을 점수로 변환 |
| `classify_improvement_type()` | `시급한 결함` / `편의 개선` 분류 |
| `_fetch_category_keywords()` | 선택적 키워드 수집 |
| `calculate_priority_score()` | 카테고리별 점수 계산 |
| `fetch()` | 최종 Top 5 반환 |
| `build_top5_slack_blocks()` | Slack Block Kit 변환 |
