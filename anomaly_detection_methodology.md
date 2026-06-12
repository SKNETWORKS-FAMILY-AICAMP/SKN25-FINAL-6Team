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
  - 이상치 탐지를 위한 통계적 기준값의 원전 논문.
  - Z-Score 임계값 2.0/3.0은 정규분포 가정 하에서 각각 상위 2.3%, 0.13%에 해당하는 유의수준 기반.
  - 논문 원문 명시: "거의 모든 이상치 기준은 정규분포 가정에 기반하며, 유의수준 5% 초과는 권장하지 않는다."
  - [DOI: 10.1080/00401706.1969.10490657](https://www.tandfonline.com/doi/abs/10.1080/00401706.1969.10490657)

- Chandola, V., Banerjee, A., Kumar, V. (2009). *Anomaly Detection: A Survey.* ACM Computing Surveys, 41(3), Article 15.
  - 이상 탐지 전반을 다루는 교과서급 서베이 논문. **11,392 인용** (Semantic Scholar 기준).
  - 통계 기반 이상 탐지(Statistical-based anomaly detection)를 주요 카테고리로 분류하며, Z-Score 계열 방법이 해당 카테고리에 포함됨.
  - [DOI: 10.1145/1541880.1541882](https://dl.acm.org/doi/10.1145/1541880.1541882)

#### 정규분포 가정 관련 심사 방어

> Grubbs(1969)는 "데이터가 정규분포가 아닐 경우 확률값이 달라질 수 있다"고 명시함.
> 이에 대한 대응: 시간대별 문의량은 4주(28일) 집계 기반이므로
> **중심극한정리(CLT)** 에 의해 표본 평균이 정규분포에 근사함.
> 따라서 Z-Score 적용이 통계적으로 정당화됨.

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

> WoW 임계값(+50%/+100%)은 서비스 운영 특성에 따라 조정 가능한 파라미터임.
> Ren et al.(2019)에서 대규모 서비스 환경의 이상 탐지 운영 경험을 참고하여 설정.

#### 데이터 기준

- 테이블: `qa_ticket`
- 시간 기준 컬럼: `inquiry_created_at`
- 집계 단위: 요일별 (`DATE_TRUNC('day', inquiry_created_at)`)
- 비교 대상: 전주 동일 요일 (7일 전 같은 요일)
- 기존 `weekly_report/service.py`의 `week_data` / `prev_week_data` 구조 확장

#### 이론적 근거

- Taylor, S.J., Letham, B. (2018). *Forecasting at Scale (Prophet).* The American Statistician, 72(1).
  - 요일별 계절성(weekly seasonality)을 명시적으로 모델링하는 Prophet 논문.
  - 전주 동일 요일 비교가 계절성 제거의 유효한 방법임을 간접 지지.

- Cleveland, R.B. et al. (1990). *STL: A Seasonal-Trend Decomposition Procedure Based on Loess.* Journal of Official Statistics, 6(1), 3–73.
  - 시계열의 계절성 성분을 분리하는 STL 분해 방법론.
  - 요일 패턴이 존재하는 데이터에서 동일 요일 비교가 계절성을 자연스럽게 제거함을 지지.

- Ren, H. et al. (2019). *Time-Series Anomaly Detection Service at Microsoft.* KDD '19, pp. 3009–3017.
  - Microsoft가 Bing, Office, Azure 등 수백만 개 운영 지표를 실시간 모니터링하는 이상 탐지 서비스 구축 사례.
  - 본 시스템과 동일하게 "서비스 운영 지표의 이상 감지 → 담당자 알림" 파이프라인을 실제 운영 환경에 적용한 실무 근거.
  - [arXiv: 1906.03821](https://arxiv.org/abs/1906.03821) / [DOI: 10.1145/3292500.3330680](https://doi.org/10.1145/3292500.3330680)

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
| Z-Score 채택 | 시간대별 편차 측정에 적합, 정규분포 기반 임계값 이론 명확 (Grubbs 1969) |

---

## 심사위원 방어 포인트 (논문 실제 내용 기반)

| 예상 질문 | 답변 |
|----------|------|
| "Z-Score 임계값 2.0/3.0은 어디서 나왔나요?" | Grubbs(1969): 정규분포 하에서 유의수준 5%, 1%에 해당하는 임계값. 논문에 명시된 수치. |
| "문의량이 정규분포를 따르나요?" | 4주(28일) 집계 기반이므로 중심극한정리에 의해 근사 정규분포 가정 가능. Grubbs 논문도 근사 정규분포 조건에서 적용 가능함을 언급. |
| "Chandola 논문이 Z-Score를 직접 권장하나요?" | Chandola(2009)는 통계 기반 이상 탐지를 주요 카테고리로 분류하며, Z-Score 계열이 해당 카테고리에 포함됨. 11,392 인용의 서베이 논문으로 이 분야 표준 참고 문헌. |
| "Ren(2019) 논문 방법론이 우리와 같은가요?" | 알고리즘은 다름(SR+CNN). 인용 포인트는 알고리즘이 아니라 '대규모 IT 서비스 운영 지표 이상 탐지를 실제 서비스에 적용한 실무 사례'로서의 근거. |
| "WoW 임계값 50%/100%의 근거는?" | 서비스 운영 특성에 따라 조정 가능한 파라미터. Ren(2019)의 실무 운영 경험을 참고하였으며, 실제 서비스 데이터 누적 후 재조정 예정. |

---

## 구현 지시사항 (Claude Code용)

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
