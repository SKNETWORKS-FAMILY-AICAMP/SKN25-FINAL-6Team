# AI 제안 권장 액션 — 방법론

## 목적

주간 집계 데이터(문의 건수, 증감률, Top 5 이슈)를 LLM에 주입하여
운영 담당자에게 **권장 액션(Recommended Actions)** 을 자동 생성한다.
생성된 권장 액션은 주간 리포트에 포함되어 Slack으로 전송된다.

---

## 신빙성 논증 구조

이 시스템의 신뢰성은 3가지 축으로 구성된다.

```
① LLM이 데이터를 근거로 분석하는가?   → RAG / Grounding
② LLM의 추론 과정이 신뢰할 수 있는가? → CoT Prompting
③ LLM 권고가 의사결정에 실효성 있는가? → DSS / XAI
```

---

## 방법론 1. Structured RAG — "데이터 기반 생성" 근거

### 개념

집계된 주간 지표(건수, 증감률, Top 5)를 프롬프트 컨텍스트에 직접 삽입한다.
LLM이 외부 지식이 아닌 **주입된 실데이터를 근거로** 권장 액션을 생성하게 한다.
이는 Structured RAG 패턴에 해당한다.

### 환각(Hallucination) 감소 근거

| 논문 | 핵심 내용 |
|------|----------|
| Mitigating Hallucinations in LLMs via RAG | RAG가 사실 정확도·신뢰성을 높이는 핵심 근거 논문 |
| Exploring RAG Solutions to Reduce Hallucinations (IEEE) | self-reflective RAG가 환각률을 5.8%까지 낮춤 |
| MEGA-RAG: Multi-evidence guided answer refinement | 다중 증거 기반 RAG로 환각률 40% 이상 감소 |

### 적용 방식

```
[컨텍스트 주입 예시]
- 이번 주 총 문의: 320건 (전주 대비 +18%)
- 결제 카테고리: 80건 (전주 대비 +32%, critical)
- Top 1 이슈: "환불 오류" 클러스터 45건
- Z-Score 이상 시간대: 14시 (Z=4.2, critical)

위 데이터를 기반으로 운영 담당자에게 권장 액션 3가지를 제시하라.
```

---

## 방법론 2. Chain-of-Thought (CoT) Prompting — "추론 일관성" 근거

### 개념

단계적 추론을 유도하는 프롬프트 구조를 사용한다.
LLM이 데이터 → 분석 → 결론 순서로 사고하도록 강제하여
추론 일관성과 출력 품질을 높인다.

### 근거 논문

| 논문 | 핵심 내용 |
|------|----------|
| RATT: A Thought Structure for Coherent and Correct LLM Reasoning (arXiv 2024) | 구조적 사고 체계로 LLM 추론 일관성·정확성 향상 |
| Chain-of-Structured-Thought (CoST) | 구조화 데이터 처리에 특화된 CoT 변형 — 스키마 정렬 출력 |

### 주의사항 및 대응

> CoT는 환각을 오히려 숨길 수 있다는 반론 존재.
> (Chain-of-Thought Obscures Hallucination Cues, arXiv)
> 따라서 **CoT + RAG 병행** 구조로 신뢰성을 최대화한다.

### 프롬프트 구조 예시

```
Step 1. 제공된 데이터에서 이상 징후를 파악하라.
Step 2. 이상 징후의 원인을 추론하라.
Step 3. 원인에 기반한 운영 액션을 제시하라.
Step 4. 각 액션의 근거 수치를 명시하라.
```

---

## 방법론 3. XAI (Explainable AI) 원칙 — "근거 명시로 신뢰 확보"

### 개념

권장 액션 출력 시 **근거 수치를 함께 병기**한다.
"왜 이 액션을 권장하는가"를 설명 가능하게 만드는 것이 XAI 원칙이다.

### 근거 논문

| 논문 | 핵심 내용 |
|------|----------|
| Explainable AI-Based Decision Support Systems (MDPI 2024) | XAI-DSS의 방법론·평가 기준 종합 리뷰 |
| Explainable AI for enhanced decision-making (ScienceDirect 2024) | 설명 가능성이 의사결정 품질에 미치는 영향 |
| "Do I Trust the AI?" — User Perception in LLM Reasoning (arXiv 2025) | 사용자가 LLM 권고를 신뢰하는 조건 분석 |

### 적용 방식

권장 액션 출력 형식에 근거 수치 필드를 포함시킨다.

```python
# 출력 형식 예시
{
    "action": "결제 오류 긴급 점검 요청",
    "reason": "결제 카테고리 이번 주 80건, 전주 대비 +32% (critical)",
    "priority": "critical"
}
```

---

## 방법론 4. DSS (Decision Support System) — "LLM 권고의 실효성" 근거

### 근거 논문

| 논문 | 핵심 내용 |
|------|----------|
| An LLM-Based Approach for Insight Generation in Data Analysis (NAACL 2025) | 집계 데이터 → LLM → 인사이트 생성 파이프라인 직접 다룸 |
| Data-to-Dashboard: Multi-Agent LLM Framework (arXiv 2025) | 데이터 → 대시보드 → 인사이트 생성 멀티에이전트 프레임워크 |
| LLMs as Decision-Making Tools in Oncology (JCO, ASCO) | LLM 제안 vs 전문가 권고 비교 — AI 제안 실효성 검증 방법론 |

> NAACL 2025와 Data-to-Dashboard가 본 시스템과 가장 직접적으로 대응.
> "집계 데이터 → LLM → 액션 출력" 파이프라인을 직접 다루는 논문.

---

## 전체 파이프라인

```
주간 집계 데이터
(건수 · 증감률 · Top5 · 이상 시간대)
        ↓
  Structured RAG
  (데이터를 컨텍스트로 주입)
        ↓
  CoT 프롬프트
  (단계적 추론 유도)
        ↓
  LLM 분석 (GPT / Claude)
        ↓
  XAI 원칙 적용
  (근거 수치 병기)
        ↓
  권장 액션 3~5개 출력
        ↓
  Slack 주간 리포트 전송
```

---

## 구현 지시사항 (Claude Code용)

### 환경

- 언어: Python
- LLM: OpenAI GPT 또는 Anthropic Claude API
- 기존 파일: `weekly_report/service.py`

### 구현할 함수 목록

1. `build_context_prompt(weekly_stats: dict) -> str`
   - 주간 집계 데이터를 받아 Structured RAG 컨텍스트 문자열 생성
   - 포함 항목: 총 건수, 카테고리별 건수/증감률, Top 5 이슈, Z-Score 이상 시간대

2. `build_cot_prompt(context: str) -> str`
   - CoT 구조 프롬프트 생성
   - Step 1~4 단계적 추론 유도 포함

3. `generate_recommended_actions(weekly_stats: dict) -> list[dict]`
   - `build_context_prompt` + `build_cot_prompt` 결합
   - LLM API 호출
   - 반환: 권장 액션 리스트 (action, reason, priority 포함)

4. 생성된 권장 액션을 기존 Slack 리포트 블록에 통합

### 반환 형식 예시

```python
# generate_recommended_actions 반환 예시
[
    {
        "rank": 1,
        "action": "결제 오류 긴급 점검 요청",
        "reason": "결제 카테고리 이번 주 80건, 전주 대비 +32% (critical 수준)",
        "priority": "critical"
    },
    {
        "rank": 2,
        "action": "오후 2시대 CS 인력 증원 검토",
        "reason": "14시 Z-Score 4.2 — 4주 평균 대비 이상 폭증 감지",
        "priority": "high"
    },
    {
        "rank": 3,
        "action": "뽑기 시스템 확률 공지 재점검",
        "reason": "뽑기 카테고리 Top 이슈 '확률 불만' 클러스터 38건 집중",
        "priority": "high"
    },
]
```

### 프롬프트 설계 원칙 (누락 엄금)

- 컨텍스트에 수치 데이터 반드시 포함 (RAG 원칙)
- 액션마다 근거 수치 병기 필수 (XAI 원칙)
- 단계적 추론 유도 포함 (CoT 원칙)
- 환각 방지를 위해 "제공된 데이터만 근거로 사용하라" 명시

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 근거 |
|----------|----------|
| "LLM이 만든 권장 액션을 믿을 수 있나요?" | RAG 논문: 실데이터 주입 시 환각률 최대 40% 감소. 외부 지식이 아닌 집계 수치 기반 생성 |
| "왜 이 액션을 권장하는지 근거가 있나요?" | XAI 원칙 적용 — 모든 액션에 근거 수치 병기. arXiv 2025: 근거 명시 시 사용자 신뢰도 상승 |
| "LLM 추론이 일관성 있나요?" | CoT 프롬프트 적용 (RATT 2024). 단, CoT 단독은 환각 은폐 위험이 있어 RAG와 병행 |
| "실제 서비스에 적용된 사례가 있나요?" | NAACL 2025, Data-to-Dashboard arXiv 2025 — 동일한 데이터→LLM→인사이트 파이프라인 논문 |
