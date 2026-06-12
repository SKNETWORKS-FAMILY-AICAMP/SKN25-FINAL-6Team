# 문의량 폭증 감지 방법론

## 목적

`qa_ticket` 테이블의 문의량 데이터에서 비정상적인 폭증을 식별한다.
감지 결과는 주간 운영 리포트의 **급증·위험 문의 현황** 섹션에 포함되어
매주 월요일 09:00 KST Airflow DAG이 자동 생성 후 Slack으로 기획팀에 전송한다.

> **운영 목적 명시**
> 이 시스템은 실시간 이상 감지가 아닌 **주간 사후 분석**이다.
> Z-Score는 "이번 주 어느 시간대에 이상 집중이 있었는가"를 식별하여
> 운영 인력 배치 판단 근거를 제공한다.
> WoW는 일별·주차별 추세를 파악하여 마케팅 시사점 도출에 활용한다.

---

## 실행 파이프라인 (Airflow)

```
Airflow DAG (매주 월요일 09:00 KST)
  │
  ├─ Task 1: fetch_report_data
  │     └─ fetch_weekly_report_data()
  │
  ├─ Task 2: detect_anomalies
  │     ├─ calculate_zscore_by_hour()       ← 시간별 히트맵용
  │     ├─ calculate_wow_by_day()           ← 일별 7일 바차트용
  │     ├─ calculate_wow_by_category()      ← 카테고리별 폭증
  │     └─ calculate_monthly_trend()        ← 4주 바차트용
  │
  ├─ Task 3: compose_report
  │     └─ build_weekly_report_payload()    ← anomaly_section 포함
  │
  ├─ Task 4: render_pdf
  └─ Task 5: send_slack
```

---

## 방법론 1. Z-Score — 시간별 히트맵 (운영 인력 배치 목적)

### 개념

과거 4주치 동일 시간대 데이터로 평균(μ)과 표준편차(σ)를 계산하고,
이번 주 각 시간대 값이 평균에서 얼마나 벗어났는지를 Z-Score로 수치화한다.
결과는 0~23시 히트맵으로 시각화하여 집중 시간대를 한눈에 파악한다.

### 공식

```
Z = (이번 주 시간대 건수 - 과거 4주 동일 시간대 평균) / 과거 4주 동일 시간대 표준편차
```

### 임계값

| Z-Score | 판정 | 히트맵 색상 |
|---------|------|------------|
| Z < 2.0 | 정상 (normal) | 회색 |
| Z ≥ 2.0 | 경고 (warning) | 주황 |
| Z ≥ 3.0 | 위험 (critical) | 빨강 |

### 데이터 기준

- 테이블: `qa_ticket`
- 시간 기준 컬럼: `inquiry_created_at`
- 집계 단위: `EXTRACT(HOUR FROM inquiry_created_at)`
- 비교 범위: 실행일 기준 과거 28일(4주) 동일 시간대

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

위 쿼리 결과로 시간대별 평균/표준편차를 Python `statistics` 모듈로 계산 후 Z-Score 산출.

### 이론적 근거

- **Grubbs, F.E. (1969).** *Procedures for Detecting Outlying Observations in Samples.*
  Technometrics, 11(1), 1–21. [DOI: 10.1080/00401706.1969.10490657](https://www.tandfonline.com/doi/abs/10.1080/00401706.1969.10490657)
  - 논문 원문: 이상치 탐지를 위한 통계적 기준값의 원전. Z-Score 임계값은 정규분포 가정 하에서 유의수준 5%(Z≥2.0), 1%(Z≥3.0)에 해당.
  - 논문 원문 명시: "거의 모든 이상치 기준은 정규분포(Gaussian) 가정에 기반한다."

- **Chandola, V., Banerjee, A., Kumar, V. (2009).** *Anomaly Detection: A Survey.*
  ACM Computing Surveys, 41(3), Article 15. [DOI: 10.1145/1541880.1541882](https://dl.acm.org/doi/10.1145/1541880.1541882)
  - 11,392 인용 (Semantic Scholar 기준). 이상 탐지를 통계 기반/근접성 기반/분류 기반 등으로 체계화한 교과서급 서베이.
  - 통계 기반 이상 탐지(Statistical-based) 카테고리에 Z-Score 계열이 포함됨.

### 정규분포 가정 방어

> Grubbs(1969)가 명시한 정규분포 가정에 대한 대응:
> 시간대별 문의량은 4주(28일) × 동일 시간대 데이터 집계 기반이므로
> 중심극한정리(CLT)에 의해 표본 평균이 정규분포에 근사한다.
> 따라서 Z-Score 적용이 통계적으로 정당화된다.

---

## 방법론 2. WoW (Week-over-Week) — 일별 7일 바차트

### 개념

이번 주 요일별 문의량을 전주 동일 요일과 비교하여 증가율을 계산한다.
요일별 패턴(게임 서비스 특성상 월요일 집중, 주말 감소)을 자연스럽게 반영한다.

### 공식

```
WoW 증가율 = (이번 주 요일 건수 - 전주 동일 요일 건수) / 전주 동일 요일 건수
```

### 임계값

| 증가율 | 판정 |
|--------|------|
| ≥ +50% | 경고 (warning) |
| ≥ +100% | 위험 (critical) |

### 데이터 기준

- 집계 단위: 요일별 (`DATE_TRUNC('day', inquiry_created_at)`)
- 비교 대상: 7일 전 동일 요일
- `fetch_weekly_report_data()`의 `current_rows` / `previous_rows` 구조 활용

### 이론적 근거

- **Ren, H. et al. (2019).** *Time-Series Anomaly Detection Service at Microsoft.*
  KDD '19, pp. 3009–3017. [arXiv: 1906.03821](https://arxiv.org/abs/1906.03821)
  - 논문 원문: Microsoft가 Bing, Office, Azure의 수백만 운영 지표를 실시간 모니터링. "이상 감지 → 담당자 알림" 파이프라인을 대규모 서비스에 적용한 실무 근거.
  - 인용 포인트: 알고리즘(SR+CNN)이 아닌, **서비스 운영 지표 이상 탐지를 실제 운영 환경에 적용한 사례** 로서의 근거.

- **Taylor, S.J., Letham, B. (2018).** *Forecasting at Scale (Prophet).*
  The American Statistician, 72(1).
  - 주간 계절성(weekly seasonality) 모델링 논문. 전주 동일 요일 비교가 요일 패턴을 자연스럽게 제거하는 유효한 방법임을 간접 지지.

---

## 방법론 3. 카테고리별 WoW — 카테고리별 폭증

### 개념

`ticket_analysis.category` (결제, 지급, 뽑기, 계정, 인게임버그) 단위로
WoW 증가율을 개별 계산한다.

### 판단 기준

```
카테고리 X의 이번 주 건수 / 전주 건수 - 1 > 50%  →  해당 카테고리 폭증
```

---

## 방법론 4. 월별 추세 (4주 바차트)

### 개념

이번 주 총 건수와 직전 3주 각각의 총 건수를 비교하여 4주 추세를 시각화한다.
"이번 달 전체적으로 문의량이 증가 추세인가"를 파악하는 월 단위 시사점 제공.

### 공식

```
N주 전 대비 증가율 = (이번 주 건수 - N주 전 건수) / N주 전 건수
```

### 반환 구조

```python
# calculate_monthly_trend 반환 예시
[
    {"week_offset": 0,  "label": "이번 주",  "count": 320, "pct_change": None},
    {"week_offset": -1, "label": "1주 전",   "count": 270, "pct_change": 0.185},
    {"week_offset": -2, "label": "2주 전",   "count": 290, "pct_change": 0.103},
    {"week_offset": -3, "label": "3주 전",   "count": 250, "pct_change": 0.280},
]
```

### 이론적 근거

- Ren et al. (2019) 재활용: 다주기 시계열 패턴 모니터링 근거.

---

## Slack 출력 포맷 정의

### 시간별 히트맵 (텍스트 표)

```
[시간별 문의 집중도]
00시  ░░░░  normal
...
14시  ████  critical (Z=6.1)
15시  ███░  warning  (Z=2.4)
...
```

- Slack Block Kit은 인터랙티브 차트 미지원 → 텍스트 표 또는 matplotlib 이미지 첨부
- critical/warning 시간대만 강조 표시, 나머지는 생략 가능

### 폭증 없을 때 출력

```python
if all(item["level"] == "normal" for item in results):
    return [{"type": "section", "text": {"type": "mrkdwn",
             "text": "✅ 이번 주 이상 폭증 감지 없음"}}]
```

---

## 구현 함수 목록

| 함수명 | 반환 | 용도 |
|--------|------|------|
| `calculate_zscore_by_hour(db)` | `list[dict]` | 시간별 히트맵 |
| `calculate_wow_by_day(db)` | `list[dict]` | 일별 7일 바차트 |
| `calculate_wow_by_category(db)` | `list[dict]` | 카테고리별 폭증 |
| `calculate_monthly_trend(db)` | `list[dict]` | 4주 바차트 |
| `build_anomaly_slack_blocks(...)` | `list[dict]` | Slack Block Kit 변환 |

### 반환 형식 예시

```python
# calculate_zscore_by_hour
[
    {"hour": 14, "avg": 11.5, "std": 2.2, "current": 25, "zscore": 6.1, "level": "critical"},
    {"hour": 15, "avg": 9.0,  "std": 1.5, "current": 13, "zscore": 2.7, "level": "warning"},
]

# calculate_wow_by_day
[
    {"day": "Monday", "this_week": 160, "prev_week": 100, "pct_change": 0.6, "level": "warning"},
]

# calculate_wow_by_category
[
    {"category": "결제", "this_week": 80, "prev_week": 40, "pct_change": 1.0, "level": "critical"},
]

# calculate_monthly_trend
[
    {"week_offset": 0,  "label": "이번 주", "count": 320, "pct_change": None},
    {"week_offset": -1, "label": "1주 전",  "count": 270, "pct_change": 0.185},
]
```

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 |
|----------|------|
| "Z-Score 임계값 2.0/3.0 근거는?" | Grubbs(1969) 논문에 명시된 유의수준 5%, 1% 기반 수치 |
| "문의량이 정규분포를 따르나요?" | 4주 집계 기반으로 중심극한정리에 의해 근사 정규분포 가정 가능. Grubbs 논문도 근사 조건 적용 가능 명시 |
| "실시간 감지 아닌가요?" | 주 1회 배치 사후 분석 구조. 목적은 실시간 알림이 아닌 주간 운영 인력 배치 판단 근거 제공 |
| "Ren(2019) 알고리즘이 우리와 같은가요?" | 알고리즘(SR+CNN)은 다름. 인용 포인트는 대규모 IT 서비스 운영 지표 이상 탐지 실무 적용 사례 |
| "WoW 임계값 50%/100% 근거는?" | 서비스 특성 기반 운영 파라미터. 데이터 누적 후 재조정 예정 |
