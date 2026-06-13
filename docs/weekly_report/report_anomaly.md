# 문의량 폭증 감지 방법론

## 목적

`qa_ticket` 테이블의 문의량 데이터에서 비정상적인 폭증을 식별한다.
감지 결과는 주간 운영 리포트의 **급증·위험 문의 현황** 섹션에 포함되어
매주 월요일 09:00 KST Airflow DAG이 자동 생성 후 Slack으로 기획팀에 전송한다.

> **운영 목적 명시**
> 실시간 이상 감지가 아닌 **주간 사후 분석**이다.
> Z-Score는 "이번 주 어느 시간대에 이상 집중이 있었는가"를 식별하여
> 운영 인력 배치 판단 근거를 제공한다.
> 일별·주차별 증감은 학술 임계값 없이 운영 경험치 기반 파라미터로 판단한다.

---

## 구현 위치

```
apps/weekly_report/db/spike_alerts.py
```

## 실행 파이프라인 (Airflow)

```
Airflow DAG (매주 월요일 09:00 KST)
  │
  ├─ Task 1: fetch_report_data       ← date_range.py 기준값 생성
  ├─ Task 2: detect_anomalies        ← spike_alerts.py 호출
  │     ├─ calculate_zscore_by_hour()
  │     ├─ calculate_daily_counts()
  │     └─ calculate_monthly_trend()
  ├─ Task 3: compose_report          ← report.py
  ├─ Task 4: render_pdf              ← pdf.py
  └─ Task 5: send_slack              ← slack.py
```

---

## 방법론 1. Z-Score — 시간별 히트맵

### 개념

과거 4주치 동일 시간대 데이터로 평균(μ)과 표준편차(σ)를 계산하고,
이번 주 각 시간대 값이 평균에서 얼마나 벗어났는지를 Z-Score로 수치화한다.
결과는 0~23시 히트맵으로 시각화하여 집중 시간대를 파악한다.

### 공식

```
Z = (이번 주 시간대 건수 - 과거 4주 동일 시간대 평균) / 과거 4주 동일 시간대 표준편차
```

### 임계값

| Z-Score | 판정 | 히트맵 색상 |
|---------|------|------------|
| Z < 2.0 | 정상 | 회색 |
| Z ≥ 2.0 | 경고 (warning) | 주황 |
| Z ≥ 3.0 | 위험 (critical) | 빨강 |

### 이론적 근거

- **Grubbs, F.E. (1969).** *Procedures for Detecting Outlying Observations in Samples.*
  Technometrics, 11(1), 1–21.
  [DOI: 10.1080/00401706.1969.10490657](https://www.tandfonline.com/doi/abs/10.1080/00401706.1969.10490657)
  - 논문 원문 직접 확인: "almost all criteria for outliers are based on an assumed underlying normal (Gaussian) population."
  - "significance levels 5%, 1% are recommended." → Z≥2.0(5%), Z≥3.0(1%) 임계값의 직접 근거.

- **Chandola, V., Banerjee, A., Kumar, V. (2009).** *Anomaly Detection: A Survey.*
  ACM Computing Surveys, 41(3), Article 15.
  [DOI: 10.1145/1541880.1541882](https://dl.acm.org/doi/10.1145/1541880.1541882)
  - 11,392 인용 (Semantic Scholar 기준). 이상 탐지 방법론 분류 체계의 교과서급 서베이.
  - 통계 기반 이상 탐지(Statistical-based) 카테고리에 Z-Score 계열이 포함됨.

### 정규분포 가정 방어

> Grubbs(1969) 원문: "When the data are not normally distributed, the probabilities will be different."
> 대응: 시간대별 문의량은 4주(28일) × 동일 시간대 집계 기반이므로
> 중심극한정리(CLT)에 의해 표본 평균이 정규분포에 근사한다.

### 구현 SQL

```sql
SELECT
    EXTRACT(HOUR FROM inquiry_created_at) AS hour,
    COUNT(*) AS cnt
FROM qa_ticket
WHERE inquiry_created_at >= NOW() - INTERVAL '28 days'
GROUP BY hour
ORDER BY hour;
```

---

## 방법론 2. 일별 건수 집계 — 7일 바차트

### 개념

이번 주 7일간 일별 문의량을 집계하여 바차트로 시각화한다.
전주 동일 요일 대비 증감을 함께 표시한다.

> **임계값은 학술 근거 없는 운영 파라미터다.**
> +50% 경고 / +100% 위험은 서비스 특성 기반 경험치이며,
> 데이터 누적 후 재조정 예정.

### 공식

```
일별 증감률 = (이번 주 요일 건수 - 전주 동일 요일 건수) / 전주 동일 요일 건수
```

### 임계값 (운영 파라미터)

| 증감률 | 판정 |
|--------|------|
| ≥ +50% | 경고 |
| ≥ +100% | 위험 |

---

## 방법론 3. 월별 추세 — 4주 바차트

### 개념

이번 주 총 건수와 직전 3주 각각의 총 건수를 집계하여 4주 추세를 시각화한다.

> **임계값 없음.** 추세 시각화 목적이며 판정 기준은 별도 적용하지 않는다.

### 반환 구조

```python
[
    {"week_offset": 0,  "label": "이번 주", "count": 320},
    {"week_offset": -1, "label": "1주 전",  "count": 270},
    {"week_offset": -2, "label": "2주 전",  "count": 290},
    {"week_offset": -3, "label": "3주 전",  "count": 250},
]
```

---

## Slack 출력 포맷

### 시간별 히트맵 (텍스트)

```
[시간별 문의 집중도]
14시  ████  critical (Z=6.1)
15시  ███░  warning  (Z=2.4)
※ 정상 시간대 생략
```

### 폭증 없을 때

```python
if all(item["level"] == "normal" for item in results):
    return [{"type": "section", "text": {"type": "mrkdwn",
             "text": "✅ 이번 주 이상 폭증 감지 없음"}}]
```

---

## 구현 함수 목록 (spike_alerts.py)

| 함수명 | 반환 | 용도 |
|--------|------|------|
| `_calculate_zscore_by_hour(window)` | `list[dict]` | 시간별 히트맵 |
| `_calculate_wow_by_day(window)` | `list[dict]` | 일별 7일 바차트 |
| `_calculate_monthly_trend(window)` | `list[dict]` | 4주 바차트 |
| `build_spike_slack_blocks(alerts)` | `list[dict]` | Slack Block Kit 변환 |
| `detect(window)` | `dict` | 세 방법론 통합 실행 진입점 |

### 반환 형식

```python
# calculate_zscore_by_hour
[
    {"hour": 14, "avg": 11.5, "std": 2.2, "current": 25, "zscore": 6.1, "level": "critical"},
    {"hour": 15, "avg": 9.0,  "std": 1.5, "current": 13, "zscore": 2.7, "level": "warning"},
]

# calculate_daily_counts
[
    {"day": "Monday", "this_week": 160, "prev_week": 100, "pct_change": 0.6, "level": "warning"},
]

# calculate_monthly_trend
[
    {"week_offset": 0,  "label": "이번 주", "count": 320},
    {"week_offset": -1, "label": "1주 전",  "count": 270},
]
```

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 |
|----------|------|
| "Z-Score 임계값 2.0/3.0 근거는?" | Grubbs(1969) 원문: 유의수준 5%, 1% 기반 수치. 직접 확인함 |
| "문의량이 정규분포를 따르나요?" | 4주 집계 기반 → 중심극한정리에 의해 근사 정규분포 가정 가능 |
| "일별/월별 임계값 근거는?" | 학술 근거 없는 운영 경험치 파라미터. 데이터 누적 후 재조정 예정 |
| "실시간 감지 아닌가요?" | 주 1회 배치 사후 분석. 목적은 운영 인력 배치 판단 근거 제공 |
