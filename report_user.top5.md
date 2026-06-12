# 유저 개선 요청 Top 5 — 우선순위 산정 방법론

## 목적

`qa_ticket` + `ticket_analysis` 테이블의 문의 데이터에서
유저가 반복적으로 요청하는 개선 사항을 자동 추출하고,
**빈도 × 심각도 가중합** 방식으로 Top 5를 산정하여 주간 리포트에 포함한다.

---

## 핵심 설계 원칙

### 왜 건수(빈도)만으로 순위를 매기면 안 되는가

게임 크래시처럼 치명적인 이슈는 소수 유저만 보고하더라도 최고 심각도다.
건수 단독 집계는 이런 크리티컬 이슈를 과소평가한다.

> 근거: Prioritization of Crowdsourced Test Reports (IEEE 2024)
> "Frequency-only 방식은 소수 보고 고심각도 이슈를 누락시킨다.
> 심각도 가중합이 필수다."

따라서 **건수 × 심각도 가중합** 구조를 채택한다.

---

## 우선순위 산정 공식

### 적용 방법론: Nielsen Severity Rating 구조 기반 가중합

```
우선순위 점수 = (발생 건수 × W₁) + (심각도 등급 × W₂)
```

| 변수 | 설명 | 기본값 |
|------|------|--------|
| 발생 건수 | 해당 카테고리/이슈의 이번 주 문의 건수 | - |
| 심각도 등급 | risk_level 기반 0~4 등급 | 아래 참고 |
| W₁ | 빈도 가중치 | 0.4 |
| W₂ | 심각도 가중치 | 0.6 |

> 근거: Nielsen, J. (1994). *Severity Ratings for Usability Problems.* Nielsen Norman Group.
> Frequency × Impact × Persistence 3축 구조에서 본 시스템에 맞게 2축으로 단순화.

---

### 심각도 등급 매핑

Nielsen Severity Rating 0~4 등급을 `risk_level`에 대응시킨다.

| Nielsen 등급 | 의미 | risk_level 매핑 |
|-------------|------|----------------|
| 4 | Catastrophe — 서비스 불가 수준 | critical |
| 3 | Major — 주요 기능 장애 | high |
| 2 | Minor — 불편하지만 우회 가능 | medium |
| 1 | Cosmetic — 사소한 불편 | low |
| 0 | 문제 아님 | - |

---

## 처리 단계 (Step-by-Step)

### Step 1. 분류 (카테고리 레이블링)

기존 LLM 분류기로 이미 부여된 카테고리 활용.

- 테이블: `ticket_analysis.category`
- 값: 결제 / 지급 / 뽑기 / 계정 / 인게임버그

> 근거: Maalej, W. et al. *On the automatic classification of app reviews.*
> 버그 리포트 / 기능 요청 / 사용자 경험 3분류 구조가 기초.
> 본 시스템은 게임 도메인에 맞게 5개 카테고리로 확장 적용.

---

### Step 2. 클러스터링 (세부 이슈 그룹화)

동일 카테고리 내 유사 문의를 의미 단위로 묶는다.

- 방법: BERTopic (BERT 임베딩 + UMAP + HDBSCAN)
- 입력: `qa_ticket.inquiry_content` (문의 본문)
- 출력: 클러스터 ID + 대표 키워드

> 근거: Topic Modeling on Customer Feedback using LDA and BERTopic
> BERTopic이 LDA 대비 의미론적 클러스터링 품질 우수.
> LDA는 단어 빈도 기반이라 짧은 문의 텍스트에 불리.

> 실무 근거: Microsoft (ML and customer support)
> 토픽 모델링으로 지원 케이스 투자 영역을 도출한 실사례.

---

### Step 3. 점수 산정

클러스터별로 우선순위 점수를 계산한다.

```python
score = (건수 × 0.4) + (심각도_등급 × 0.6)
```

- 건수: 해당 클러스터에 속한 `qa_ticket` 건수
- 심각도 등급: `ticket_analysis.risk_level` → Nielsen 등급으로 변환
- W₁=0.4, W₂=0.6 (심각도 우선 정책 반영, 조정 가능)

> 근거: Ngo, M. et al. (IEEE 2024). *Prioritization of Crowdsourced Test Reports Based on Defect Severity and Frequency Weighting.*
> 심각도+빈도 동시 고려 다목적 우선순위 알고리즘.

---

### Step 4. Top 5 추출

점수 내림차순 정렬 후 상위 5개 추출.

```python
top5 = sorted(cluster_scores, key=lambda x: x["score"], reverse=True)[:5]
```

---

### Step 5. 설계/편의 구분 (선택적 확장)

Top 5 결과를 Kano 모델 기준으로 추가 분류 가능.

| Kano 유형 | 설명 | 예시 |
|----------|------|------|
| 기본 속성 (Must-be) | 없으면 불만, 있어도 당연 | 결제 오류 수정 |
| 성능 속성 (Performance) | 많을수록 만족도 상승 | 로딩 속도 개선 |
| 매력 속성 (Attractive) | 있으면 기쁨, 없어도 무방 | 신규 편의 기능 |

> 근거: Martens, D. et al. *Automatically Classifying Kano Model Factors in App Reviews.* arXiv.

---

## 구현 지시사항 (Claude Code용)

### 환경

- 언어: Python
- DB: PostgreSQL
- 기존 파일: `weekly_report/service.py`
- BERTopic 라이브러리 사용 (`pip install bertopic`)

---

### 구현할 함수 목록

1. `get_risk_level_score(risk_level: str) -> int`
   - risk_level 문자열을 Nielsen 0~4 등급 정수로 변환
   - critical=4, high=3, medium=2, low=1, 나머지=0

2. `cluster_inquiries(db) -> list[dict]`
   - `qa_ticket.inquiry_content` 텍스트를 BERTopic으로 클러스터링
   - 반환: 클러스터 ID, 대표 키워드, 소속 ticket_id 목록

3. `calculate_priority_score(db) -> list[dict]`
   - 클러스터별 건수 + 평균 심각도 등급 계산
   - `score = (건수 × 0.4) + (심각도_등급 × 0.6)` 적용
   - 반환: 클러스터별 점수, 카테고리, 건수, 심각도, 점수

4. `get_top5_improvements(db) -> list[dict]`
   - `calculate_priority_score` 결과를 점수 내림차순 정렬
   - 상위 5개 반환
   - 기존 weekly_report Slack 전송 흐름에 통합

---

### 반환 형식 예시

```python
# get_top5_improvements 반환 예시
[
    {
        "rank": 1,
        "category": "결제",
        "topic_keywords": ["환불", "결제 오류", "카드"],
        "count": 80,
        "severity_score": 4,
        "priority_score": 74.4,
        "level": "critical"
    },
    {
        "rank": 2,
        "category": "인게임버그",
        "topic_keywords": ["크래시", "튕김", "재시작"],
        "count": 30,
        "severity_score": 4,
        "priority_score": 50.4,
        "level": "critical"
    },
]
```

---

## 방법론 선택 근거 요약

| 항목 | 선택 | 이유 |
|------|------|------|
| 우선순위 공식 | Nielsen Severity Rating 기반 가중합 | 빈도+심각도 동시 반영, 업계 표준 |
| 클러스터링 | BERTopic | 짧은 한국어 문의 텍스트에 의미론적 클러스터링 적합 |
| 건수 단독 미채택 | - | IEEE 2024: 크리티컬 이슈 소수 보고 시 누락 위험 |
| Kano 분류 | 선택적 확장 | Top 5 결과의 추가 맥락 제공용 |

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 근거 |
|----------|----------|
| "왜 건수만으로 안 뽑았나요?" | IEEE 2024: 심각도 가중합 없으면 크리티컬 이슈 누락 |
| "가중치 0.4/0.6은 어떻게 정했나요?" | Nielsen Severity 구조 기반, 심각도 우선 정책 반영. 서비스 특성에 따라 조정 가능한 파라미터 |
| "BERTopic을 왜 썼나요?" | LDA 대비 짧은 텍스트 의미론적 클러스터링 품질 우수 (BERTopic 논문 근거) |
| "Nielsen은 UX 방법론 아닌가요?" | 맞습니다. 빈도×심각도 가중합 구조 자체를 차용했으며, 게임 CS 도메인에 맞게 risk_level 매핑으로 재해석했습니다 |
