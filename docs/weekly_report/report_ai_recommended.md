# AI 제안 권장 액션 — 방법론

## 목적

주간 집계 데이터(총 건수, 전주 대비 증감, 폭증 감지 결과, Top 5 이슈)를
LLM에 주입하여 기획팀이 **다음 주 운영에서 즉시 실행할 수 있는 액션 3~5개**를 자동 생성한다.

> **수신자 전제: 기획팀**
> 단순 CS 대응 지시가 아닌 마케팅 시사점과 운영 전략 관점의 액션을 포함해야 한다.
> 예: "결제 오류 집중 → 해당 주 결제 관련 프로모션 일시 중단 검토"

---

## 구현 위치

```
apps/weekly_report/backend/ai_summary.py
```

---

## 실행 위치 (Airflow)

```python
# Airflow DAG (매주 월요일 09:00 KST)
import report

result = report.run(
    days=7,
    render_pdf=True,
    send_to_slack=True,
    slack_channel="#ops-weekly",
)
# generate_ai_actions()는 report.run() 내부에서 모든 집계/폭증감지/Top5 완료 후 마지막에 호출됨
```

---

## 근거 논문 (1개)

> **Sánchez Pérez, A., Boukhary, A., Papotti, P., Castejón Lozano, L., Elwood, A. (2025).**
> *An LLM-Based Approach for Insight Generation in Data Analysis.*
> NAACL-HLT 2025, pp. 562–582. Association for Computational Linguistics.
> [https://aclanthology.org/2025.naacl-long.24/](https://aclanthology.org/2025.naacl-long.24/)
> [DOI: 10.18653/v1/2025.naacl-long.24](https://doi.org/10.18653/v1/2025.naacl-long.24)
>
> 논문 원문 직접 확인:
> "Given a multi-table database as input, our method leverages LLMs to produce
> **concise, text-based insights** that reflect interesting patterns in the tables."
>
> 프레임워크 구성 (논문 Figure 1):
> Hypothesis Generator → Query Agent (SQL 생성) → Summarization
>
> 본 시스템과 동일한 구조:
> 집계 DB → LLM → 텍스트 액션 출력
>
> 평가 기준 (논문 원문): correctness + insightfulness 두 축으로 평가.
> 본 시스템도 동일하게 수치 정확성 + 실행 가능성 두 축으로 출력 품질 판단.

---

## 입력 데이터 정의

```python
# ai_summary.py → generate_ai_actions(report_payload) 입력
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
        "critical_categories": ["결제"]
    },
    "top5_improvements": [...],       # top_requests.py 결과
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
마케팅 시사점을 반드시 1개 이상 포함하세요.
반드시 제공된 수치 데이터만 근거로 사용하고, 외부 추측을 포함하지 마세요.
```

### 유저 프롬프트

```
[이번 주 데이터]
- 총 문의: {total_count}건 (전주 대비 {pct_change:+.1%})
- 폭증 감지: {critical_items}
- 카테고리 분포: {category_distribution}
- 유저 개선 요청 Top 3: {top3}

위 데이터를 근거로 기획팀을 위한 다음 주 운영 액션 3~5개를 제안하라.
각 액션에 근거 수치를 반드시 명시하라.
마케팅 시사점을 1개 이상 포함하라.

출력 형식(JSON만 반환):
{"headline": "...", "actions": [{"rank":1, "category":"...", "action":"...", "reason":"..."}]}
```

---

## 출력 형식

```python
{
    "headline": "결제 오류 집중 대응 및 뽑기 시스템 투명성 강화 권장",
    "actions": [
        {
            "rank": 1,
            "category": "결제",
            "action": "결제 오류 원인 분석 후 핫픽스 일정 수립",
            "reason": "전주 대비 +82% 폭증, critical 비율 1위."
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
            "reason": "확률 불만 클러스터 38건 집중."
        },
    ]
}
```

---

## Airflow 연동 (report.py)

```python
import report

result = report.run(
    days=7,
    render_pdf=True,
    send_to_slack=True,
    slack_channel="#ops-weekly",
)
# generate_ai_actions()는 report.run() 내부에서 마지막에 호출됨
```

---

## 프롬프트 설계 원칙

- 수치 데이터 반드시 포함 (환각 방지)
- 액션마다 근거 수치 병기 필수
- "제공된 데이터만 근거로 사용하라" 명시
- 마케팅 시사점 1개 이상 포함 지시

---

## 심사위원 방어 포인트

| 예상 질문 | 답변 |
|----------|------|
| "LLM 출력을 믿을 수 있나요?" | 입력을 정형 수치로 한정하여 환각 범위 제한. 최종 의사결정은 담당자가 수행 |
| "근거 논문이 있나요?" | NAACL 2025: 동일한 멀티테이블 DB → LLM → 텍스트 인사이트 파이프라인 직접 다룬 논문. ACL Anthology 등재, DOI 부여 |
| "LLM이 틀린 액션을 제안하면?" | 액션마다 근거 수치 병기. 담당자가 수치 확인 후 판단 가능한 구조 |
