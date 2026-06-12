# AI 제안 권장 액션 — 방법론

## 목적

주간 집계 데이터(총 건수, 전주 대비 증감, 폭증 감지 결과, Top 5 이슈)를
LLM에 주입하여 기획팀이 **다음 주 운영에서 즉시 실행할 수 있는 액션 3~5개**를 자동 생성한다.

> **수신자 전제: 기획팀**
> CS 담당자가 아닌 기획팀에 전달되므로, 단순 CS 대응 지시가 아닌
> **마케팅 시사점과 운영 전략** 관점의 액션을 포함해야 한다.
> 예: "결제 오류 집중 → 해당 주 결제 관련 프로모션 일시 중단 검토"

---

## 실행 위치 (Airflow)

```
Task 3: compose_report (마지막 단계)
  └─ generate_ai_actions(report_payload)
       ← 모든 집계/폭증감지/Top5 완료 후 LLM 호출
```

---

## 신빙성 논증 구조

```
① LLM이 데이터를 근거로 분석하는가?   → Structured RAG (Lewis et al. 2020)
② LLM 추론이 일관성 있는가?           → CoT Prompting (Zhang et al. RATT 2024)
③ 데이터→인사이트 파이프라인이 유효한가? → NAACL 2025 직접 대응 논문
```

---

## 방법론 1. Structured RAG — 데이터 기반 생성

### 개념

주간 집계 수치를 프롬프트 컨텍스트에 직접 삽입한다.
LLM이 외부 지식이 아닌 **실데이터를 근거로** 권장 액션을 생성하게 한다.

> **근거: Lewis, P. et al. (2020).** *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.*
> NeurIPS 2020, pp. 9459–9474. [arXiv: 2005.11401](https://arxiv.org/abs/2005.11401)
> 논문 원문: "RAG models generate more **specific, diverse and factual** language
> than a state-of-the-art parametric-only seq2seq baseline."
> 외부 지식 없이 파라미터만 사용할 때보다 실데이터 주입 시 사실 정확도 향상.
> 본 시스템은 DB 집계 수치를 컨텍스트로 직접 삽입하는 Structured RAG 패턴.

---

## 방법론 2. Chain-of-Thought (CoT) — 추론 일관성

### 개념

단계적 추론을 유도하는 프롬프트 구조를 사용한다.
데이터 → 분석 → 결론 순서로 사고하도록 강제하여 출력 일관성을 높인다.

> **근거: Zhang, J. et al. (2024/2025).** *RATT: A Thought Structure for Coherent and Correct LLM Reasoning.*
> AAAI 2025, Vol. 39(25), pp. 26733–26741. [arXiv: 2406.02746](https://arxiv.org/abs/2406.02746)
> 논문 원문: "RATT performs planning and lookahead to explore multiple potential reasoning steps,
> and integrates the fact-checking ability of RAG with LLM's ability to assess overall strategy."
> 구조적 사고 체계가 LLM의 논리적 일관성과 사실 정확성을 동시에 향상시킴.

> **주의:** CoT 단독은 환각을 숨길 수 있음(Chain-of-Thought Obscures Hallucination Cues, arXiv).
> 따라서 **RAG + CoT 병행** 구조로 신뢰성 최대화.

---

## 방법론 3. DSS (Decision Support System) — 실효성 근거

> **근거: Sánchez Pérez, A. et al. (2025).** *An LLM-Based Approach for Insight Generation in Data Analysis.*
> NAACL-HLT 2025, pp. 562–582. [ACL Anthology](https://aclanthology.org/2025.naacl-long.24/)
> 논문 원문: "Given a multi-table database as input, our method leverages LLMs to produce
> **concise, text-based insights** that reflect interesting patterns in the tables."
> 프레임워크 구성: Hypothesis Generator → Query Agent(SQL 생성) → Summarization.
> 본 시스템과 동일한 "집계 DB → LLM → 텍스트 인사이트" 파이프라인을 직접 다루는 논문.
> [DOI: 10.18653/v1/2025.naacl-long.24](https://doi.org/10.18653/v1/2025.naacl-long.24)

---

## 입력 데이터 정의

```python
report_payload = {
    "summary": {
        "total_count": 320,
        "prev_total": 270,
        "pct_change": 0.185
    },
    "comparisons": [
        {"category": "결제", "this_week": 80, "prev_week": 44, "pct_change": 0.818}
    ],
    "anomaly_section": {
        "critical_hours": [14, 15],
        "wow_critical_days": ["Monday"],
        "wow_critical_categories": ["결제"]
    },
    "top5_improvements": [...],          # get_top5_improvements() 결과
    "category_distribution": {
        "결제": 80, "지급": 30, "뽑기": 60, "계정": 50, "인게임버그": 100
    }
}
```

---

## 프롬프트 구조

### 시스템 프롬프트

```
당신은 게임 서비스 CS 데이터를 분석하는 운영 전략 어시스턴트입니다.
수신자는 기획팀이며, 데이터 기반으로 다음 주에 즉시 실행 가능한 액션을 제안해야 합니다.
마케팅 시사점(어떤 카테고리에 자원을 집중할지, 프로모션 타이밍 등)을 포함하세요.
반드시 제공된 수치 데이터만 근거로 사용하고, 외부 추측을 포함하지 마세요.
```

### 유저 프롬프트 구성 (CoT 구조)

```
[Step 1] 아래 이번 주 데이터에서 이상 징후를 파악하라.
- 총 문의: {total_count}건 (전주 대비 {pct_change:+.1%})
- 폭증 감지: {critical_items}
- 카테고리 분포: {category_distribution}

[Step 2] 이상 징후의 원인을 추론하라.

[Step 3] 기획팀을 위한 다음 주 운영 액션 3~5개를 제안하라.
마케팅 시사점을 반드시 1개 이상 포함하라.

[Step 4] 각 액션의 근거 수치를 명시하라.

출력 형식(JSON만 반환, 마크다운 코드블록 없이):
{"headline": "...", "actions": [{"rank":1, "category":"...", "action":"...", "reason":"..."}]}
```

---

## 출력 형식 정의

```python
# generate_ai_actions 반환 예시
{
    "headline": "결제 오류 집중 대응 및 뽑기 시스템 투명성 강화 권장",
    "actions": [
        {
            "rank": 1,
            "category": "결제",
            "action": "결제 오류 원인 분석 후 핫픽스 일정 수립",
            "reason": "전주 대비 +82% 폭증, critical 비율 1위. 즉시 대응 필요."
        },
        {
            "rank": 2,
            "category": "마케팅",
            "action": "결제 관련 프로모션 일시 보류 검토",
            "reason": "결제 오류 폭증 기간 중 프로모션 진행 시 CS 부담 가중 위험."
        },
        {
            "rank": 3,
            "category": "뽑기",
            "action": "확률 공개 공지 강화 및 인앱 안내 업데이트",
            "reason": "뽑기 확률 불만 클러스터 38건 집중. 투명성 개선이 재방문율에 영향."
        },
    ]
}
```

---

## Airflow 연동

```python
@task(task_id="compose_report")
def compose_report(data: dict) -> dict:
    payload = build_weekly_report_payload(data)
    payload["top5"] = get_top5_improvements(db)
    payload["ai_actions"] = generate_ai_actions(payload)  # 마지막 호출
    return payload
```

---

## 프롬프트 설계 원칙 (누락 엄금)

- 컨텍스트에 수치 데이터 반드시 포함 (RAG 원칙)
- 액션마다 근거 수치 병기 필수
- CoT 단계적 추론 유도 포함
- "제공된 데이터만 근거로 사용하라" 명시 (환각 방지)
- 마케팅 시사점 1개 이상 포함 지시 (기획팀 수신자 원칙)

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 |
|----------|------|
| "LLM 출력을 믿을 수 있나요?" | Structured RAG: 실데이터 주입으로 외부 추측 차단. 최종 의사결정은 담당자가 수행 |
| "RAG 논문이 이 시스템에 직접 적용되나요?" | Lewis(2020): 파라미터만 사용할 때보다 외부 데이터 주입 시 사실 정확도 향상 입증. 본 시스템의 수치 주입 방식이 동일 원리 |
| "가장 직접적인 근거 논문은?" | NAACL 2025(Sánchez Pérez et al.): 멀티테이블 DB → LLM → 텍스트 인사이트 파이프라인을 직접 다룬 논문. ACL Anthology 등재, DOI 부여 |
| "CoT가 오히려 환각을 숨기지 않나요?" | 알고 있음. 그래서 RAG + CoT 병행 구조. RATT(2024)가 이 조합의 근거 |
| "기획팀이 이걸 실제로 쓸 수 있나요?" | 액션마다 근거 수치 병기(XAI 원칙). 담당자가 판단 가능한 형태로 제공 |
