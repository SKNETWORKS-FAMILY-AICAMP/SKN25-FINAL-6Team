# 이상 감지 방식

## 구현 위치

- `apps/weekly_report/db/spike_alerts.py`

## 목적

주간 리포트용 이상 감지 데이터를 만든다.

현재 구현은 실시간 모니터링이 아니라 **주간 리포트 시점의 배치형 요약**이다.

## 사용 데이터

- `qa_ticket.inquiry_created_at`

현재 이상 감지는 `qa_ticket`만 사용한다.

## 감지 방법

### 1. 시간대별 Z-Score

현재 주간의 시간대별 티켓 수를, 과거 4주 동일 시간대 평균/표준편차와 비교한다.

공식:

```text
zscore = (current_count - average(past_counts)) / stddev(past_counts)
```

임계치:

- `zscore >= 2.0` -> `warning`
- `zscore >= 3.0` -> `critical`

출력 필드:

- `hour`
- `avg`
- `std`
- `current`
- `zscore`
- `level`

### 2. 요일별 WoW 증가율

현재 주간과 직전 주간의 같은 요일 건수를 비교한다.

공식:

```text
pct_change = (this_week - prev_week) / prev_week
```

임계치:

- `pct_change >= 0.5` -> `warning`
- `pct_change >= 1.0` -> `critical`

출력 필드:

- `dow`
- `day`
- `this_week`
- `prev_week`
- `pct_change`
- `level`

### 3. 최근 4주 추세

현재 주 포함 최근 4개 주간의 총 건수를 보여준다.

이 값은 추세 시각화용이며 별도 경보 임계치는 없다.

출력 필드:

- `week_offset`
- `label`
- `count`

## 반환 구조

```python
{
    "hourly": [...],
    "daily": [...],
    "monthly": [...],
}
```

## 관련 함수

| 함수 | 역할 |
| --- | --- |
| `_calculate_zscore_by_hour()` | 시간대별 이상 감지 |
| `_calculate_wow_by_day()` | 요일별 전주 대비 비교 |
| `_calculate_monthly_trend()` | 최근 4주 추세 |
| `build_spike_slack_blocks()` | Slack 메시지용 블록 생성 |
| `detect()` | 통합 진입점 |
