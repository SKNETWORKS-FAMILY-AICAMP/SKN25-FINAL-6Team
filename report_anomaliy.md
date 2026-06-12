# 문의량 폭증 감지 방법론

## 목적

`qa_ticket` 테이블의 문의량 데이터에서 비정상적인 폭증을 자동 감지한다.
감지 결과는 주간 리포트(`weekly_report/service.py`)에 통합하여 Slack으로 전송한다.

---

## 사용 방법론 2가지

### 1. Z-Score — 시간별 폭증 감지

#### 개념

과거 4주치 동일 시간대 데이터로 평균(μ)과 표준편차(σ)를 계산하고,
이번 주 값이 평균에서 얼마나 벗어났는지를 Z-Score로 수치화한다.

#### 공식

```
Z = (이번 주 관측값 - 과거 4주 평균) / 과거 4주 표준편차
```

#### 임계값

| Z-Score | 판정 |
|---------|------|
| Z ≥ 2.0 | 경고 (warning) |
| Z ≥ 3.0 | 위험 (critical) — 폭증 |

#### 데이터 기준

- 테이블: `qa_ticket`
- 시간 기준 컬럼: `inquiry_created_at`
- 집계 단위: `EXTRACT(HOUR FROM inquiry_created_at)`
- 비교 범위: 현재 시점 기준 과거 28일(4주)의 동일 시간대

#### 구현 SQL (참고)

```sql
SELECT
    EXTRACT(HOUR FROM inquiry_created_at) AS hour,
    COUNT(*) AS cnt
FROM qa_ticket
WHERE inquiry_created_at >= NOW() - INTERVAL '28 days'
GROUP BY hour
ORDER BY hour;
```

위 쿼리 결과로 시간대별 평균/표준편차를 Python에서 계산 후 Z-Score 산출.

#### 이론적 근거

- Grubbs, F.E. (1969). *Procedures for Detecting Outlying Observations in Samples.* Technometrics, 11(1), 1–21.
- Chandola, V., Banerjee, A., Kumar, V. (2009). *Anomaly Detection: A Survey.* ACM Computing Surveys, 41(3). (6,000+ 인용)

---

### 2. WoW (Week-over-Week) 비교 — 일별 폭증 감지

#### 개념

이번 주 특정 요일의 문의량을 전주 동일 요일과 비교하여 증가율을 계산한다.
요일별 패턴(월요일 폭증, 주말 감소 등 게임 서비스 특성)을 자연스럽게 반영한다.

#### 공식

```
WoW 증가율 = (이번 주 요일별 건수 - 전주 동일 요일 건수) / 전주 동일 요일 건수
```

#### 임계값

| 증가율 | 판정 |
|--------|------|
| ≥ +50% | 경고 (warning) |
| ≥ +100% | 위험 (critical) — 폭증 |

#### 데이터 기준

- 테이블: `qa_ticket`
- 시간 기준 컬럼: `inquiry_created_at`
- 집계 단위: 요일별 (`DATE_TRUNC('day', inquiry_created_at)`)
- 비교 대상: 전주 동일 요일 (7일 전 같은 요일)
- 기존 `weekly_report/service.py`의 `week_data` / `prev_week_data` 구조 확장

#### 이론적 근거

- Taylor, S.J., Letham, B. (2018). *Forecasting at Scale (Prophet).* The American Statistician, 72(1).
- Cleveland, R.B. et al. (1990). *STL: A Seasonal-Trend Decomposition Procedure Based on Loess.* Journal of Official Statistics, 6(1), 3–73.

---

### 3. 카테고리별 폭증 감지 (WoW 확장)

#### 개념

`ticket_analysis.category` (결제, 지급, 뽑기, 계정, 인게임버그) 단위로
WoW 증가율을 개별 계산한다. `risk_level`(critical/high) 가중치를 선택적으로 적용 가능.

#### 판단 기준

```
카테고리 X의 이번 주 건수 / 전주 건수 - 1 > 50%  →  해당 카테고리 폭증
```

---

## 방법론 선택 근거 요약

| 항목 | 이유 |
|------|------|
| IQR 미채택 | 카테고리별 데이터 규모가 작을 경우 기준이 불안정함 |
| WoW 채택 | 기존 service.py에 week_data 비교 구조가 이미 존재, 확장 용이 |
| Z-Score 채택 | 시간대별 편차 측정에 적합, 정규분포 기반 임계값 이론 명확 |

---

## 구현 지시사항 (Claude Code용)

아래 조건으로 구현해주세요.

### 환경

- 언어: Python
- DB: PostgreSQL
- ORM 또는 raw SQL 모두 가능
- 기존 파일: `weekly_report/service.py`

### 구현할 함수 목록

1. `calculate_zscore_by_hour(db) -> list[dict]`
   - 과거 28일 데이터를 시간대별로 집계
   - 각 시간대의 평균/표준편차 계산
   - 이번 주 각 시간대 Z-Score 반환
   - Z ≥ 2.0이면 warning, Z ≥ 3.0이면 critical 포함

2. `calculate_wow_by_day(db) -> list[dict]`
   - 이번 주 요일별 건수 vs 전주 동일 요일 건수 비교
   - WoW 증가율 계산
   - ≥ 50% warning, ≥ 100% critical 포함

3. `calculate_wow_by_category(db) -> list[dict]`
   - ticket_analysis.category 단위로 WoW 계산
   - 결과에 category명, 이번 주 건수, 전주 건수, 증가율, 판정 포함

4. 위 3개 함수 결과를 종합하여 Slack 메시지 블록에 포함시키는 로직
   - 기존 weekly_report Slack 전송 흐름에 통합

### 반환 형식 예시

```python
# calculate_zscore_by_hour 반환 예시
[
    {"hour": 14, "avg": 11.5, "std": 2.2, "current": 25, "zscore": 6.1, "level": "critical"},
    {"hour": 15, "avg": 9.0, "std": 1.5, "current": 10, "zscore": 0.7, "level": "normal"},
]

# calculate_wow_by_day 반환 예시
[
    {"day": "Monday", "this_week": 160, "prev_week": 100, "pct_change": 0.6, "level": "warning"},
]

# calculate_wow_by_category 반환 예시
[
    {"category": "결제", "this_week": 80, "prev_week": 40, "pct_change": 1.0, "level": "critical"},
]
```
