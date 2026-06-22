# AI 월 운영비 통합 추정

## 문서 목적

이 문서는 기존 두 문서에 흩어진 비용 추정 내용을 중복 없이 합쳐, `cs_auto`와 `chatbot`의 월 운영비를 한 번에 볼 수 있도록 정리한 통합본이다.

- `cs_auto` 월 운영비 추정
- `chatbot` 월 운영비 추정
- 공통 모델 단가와 가정
- 비용을 키우는 핵심 요인

기준값:

- 기준일: `2026-06-22`
- 일 문의 수: `150건`
- 월 문의 수: `4,500건`
- 성격: 실사용 청구 로그가 아니라 현재 코드 구조와 모델 설정 기반 추정치

제외 범위:

- 서버, DB, 스토리지, 네트워크 등 인프라 비용
- 운영자 수동 검수 인건비
- 실제 벤더 청구 오차

## 1. 공통 모델 및 단가 기준

현재 문서에서 공통으로 사용하는 기본 단가는 아래와 같다.

| Model | Input / 1M tokens | Output / 1M tokens |
| --- | ---: | ---: |
| `gpt-4o` | `$2.50` | `$10.00` |
| `gpt-4o-mini` | `$0.15` | `$0.60` |
| `text-embedding-3-small` | `$0.02` | `$0.00` |

근거:

- [common/observability/logger.py](/C:/SKN25-FINAL-6Team/common/observability/logger.py:34)

공통 사용 모델:

- 생성 모델: `gpt-4o`
- 임베딩 모델: `text-embedding-3-small`

추가 참고:

- `chatbot`에는 safety moderation으로 `omni-moderation-latest`가 포함된다.
- 다만 현재 repo 내부 비용표에는 moderation 단가가 등록되어 있지 않아 아래 `chatbot` 추정치는 moderation 비용을 사실상 제외한 값이다.

근거:

- [common/llm/client.py](/C:/SKN25-FINAL-6Team/common/llm/client.py:26)
- [common/llm/client.py](/C:/SKN25-FINAL-6Team/common/llm/client.py:37)
- [apps/chatbot/backend/README.md](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/README.md:392)
- [apps/chatbot/backend/README.md](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/README.md:393)
- [apps/chatbot/backend/safety/safety_layer.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/safety/safety_layer.py:27)

## 2. `cs_auto` 월 운영비 추정

### 포함 범위

- `analysis_agent` 일배치
- `answer_agent` 일배치
- `weekly_report` AI 작업

근거:

- [apps/cs_auto/backend/airflow/analysis_agent_dag.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/airflow/analysis_agent_dag.py:27)
- [apps/cs_auto/backend/airflow/answer_agent_dag.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/airflow/answer_agent_dag.py:27)
- [apps/weekly_report/airflow/weekly_report_dag.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/airflow/weekly_report_dag.py:24)

### 처리 구조

`cs_auto`는 보통 문의 1건이 아래 두 단계를 거친다.

1. `analysis_agent`
2. `answer_agent`

추가로 주간 리포트 DAG에서 소규모 AI 호출이 발생한다.

### `analysis_agent` 추정 비용

`analysis_agent`는 문의 1건당 사실상 아래 2회 호출로 본다.

1. category 분류
2. routing_target 결정

근거:

- [apps/cs_auto/backend/agents/analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/analysis_agent.py:328)
- [apps/cs_auto/backend/agents/analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/analysis_agent.py:338)

가정:

- category 분류: 입력 `1,100`, 출력 `60`
- routing 결정: 입력 `1,300`, 출력 `80`
- 총합: 입력 `2,400`, 출력 `140`

추정 비용:

- 1건 평균: `약 $0.00740`
- 월 비용: `4,500 x 0.00740 = $33.30/월`

### `answer_agent` 추정 비용

`answer_agent`는 `routing_target`에 따라 비용 차이가 크다.

운영 분포 가정:

| routing_target | 비중 |
| --- | ---: |
| `doc_only` | 68.8% |
| `DB_only` | 14.0% |
| `DB&DOC` | 8.4% |
| `fixed_answer` | 8.8% |

근거:

- [apps/cs_auto/PERFORMANCE_METRICS_INTERPRETATION.md](/C:/SKN25-FINAL-6Team/apps/cs_auto/PERFORMANCE_METRICS_INTERPRETATION.md)

경로별 평균 비용 가정:

| 경로 | 1건 평균 비용 |
| --- | ---: |
| `doc_only` | `$0.02110` |
| `DB_only` | `$0.01400` |
| `DB&DOC` | `$0.02700` |
| `fixed_answer` | `$0.00895` |

핵심 호출 근거:

- [apps/cs_auto/backend/agents/tool/docsearch.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/tool/docsearch.py:98)
- [apps/cs_auto/backend/agents/tool/docsearch.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/tool/docsearch.py:134)
- [apps/cs_auto/backend/agents/tool/docsearch.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/tool/docsearch.py:146)
- [apps/cs_auto/backend/agents/tool/dbsearch.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/tool/dbsearch.py:24)
- [apps/cs_auto/backend/agents/tool/dbsearch.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/tool/dbsearch.py:342)
- [apps/cs_auto/backend/agents/answer_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/answer_agent.py:375)
- [apps/cs_auto/backend/agents/answer_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/answer_agent.py:399)

가중 평균 결과:

- 1건 평균: `약 $0.01954`
- 월 비용: `4,500 x 0.01954 = $87.93/월`

### `weekly_report` 추정 비용

주간 리포트의 AI 비용은 티켓당 비용보다 DAG당 고정비 성격이 강하다.

주요 호출:

1. AI 추천 액션 생성
2. 검토용 행 해석 생성

근거:

- [apps/weekly_report/report.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/report.py:67)
- [apps/weekly_report/build/payload.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/build/payload.py:153)
- [apps/weekly_report/build/payload.py](/C:/SKN25-FINAL-6Team/apps/weekly_report/build/payload.py:154)

월 환산:

- AI 추천 액션: `$0.0267/월`
- 검토용 행 해석: `$0.0753/월`
- 합계: `약 $0.10/월`

### `cs_auto` 최종 추정

| 구성 | 월 비용 |
| --- | ---: |
| `analysis_agent` | `$33.30` |
| `answer_agent` | `$87.93` |
| `weekly_report` AI | `$0.10` |
| 합계 | `$121.33/월` |

해석:

- 비용 대부분은 `answer_agent`에서 발생한다.
- 그 안에서도 `doc_only`, `DB&DOC` 경로가 핵심 비용원이다.
- 주간 리포트 AI 비용은 전체에서 거의 무시 가능한 수준이다.

## 3. `chatbot` 월 운영비 추정

### 처리 구조

현재 워크플로우는 [workflow.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/chains/workflow.py:1) 기준으로 `ticket_preprocess -> category agent -> draft_persistence -> safety_layer -> ticket_completion` 흐름이다.

문의 유형별 핵심 경로:

- FAQ: enrichment, embedding, rerank, answer generation, retry 가능성
- Payment: intent fallback 가능, reasoning agent 중심
- Bug: reasoning agent 중심, 일부 FAQ precheck 추가
- VOC: 고정 응답 위주

근거:

- [common/retrieval/vector_tools.py](/C:/SKN25-FINAL-6Team/common/retrieval/vector_tools.py:170)
- [common/retrieval/vector_tools.py](/C:/SKN25-FINAL-6Team/common/retrieval/vector_tools.py:319)
- [common/retrieval/vector_tools.py](/C:/SKN25-FINAL-6Team/common/retrieval/vector_tools.py:793)
- [apps/chatbot/backend/generation/faq_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/faq_agent.py:398)
- [apps/chatbot/backend/generation/faq_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/faq_agent.py:460)
- [apps/chatbot/backend/generation/faq_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/faq_agent.py:544)
- [apps/chatbot/backend/generation/payment_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/payment_agent.py:152)
- [apps/chatbot/backend/generation/payment_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/payment_agent.py:453)
- [apps/chatbot/backend/generation/bug_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/bug_agent.py:129)
- [apps/chatbot/backend/generation/bug_agent.py](/C:/SKN25-FINAL-6Team/apps/chatbot/backend/generation/bug_agent.py:370)

### 문의 유형별 평균 비용

운영 평균 추정치는 아래와 같다.

| 문의 유형 | 1건 평균 비용 | 월 4,500건 단독 유입 시 비용 |
| --- | ---: | ---: |
| FAQ | `$0.016` | `$72.00/월` |
| Payment | `$0.006` | `$27.00/월` |
| Bug | `$0.008` | `$36.00/월` |
| VOC | `$0.003` | `$13.50/월` |

해석:

- FAQ가 가장 비싸다.
- Payment와 Bug는 reasoning 중심이라 중간 수준이다.
- VOC는 가장 저렴하다.

### 혼합 운영 시나리오

예시 분포:

- FAQ 60%
- Payment 20%
- Bug 15%
- VOC 5%

월 4,500건 기준 계산:

| 문의 유형 | 월 건수 | 1건 평균 비용 | 월 비용 |
| --- | ---: | ---: | ---: |
| FAQ | 2,700 | `$0.016` | `$43.20` |
| Payment | 900 | `$0.006` | `$5.40` |
| Bug | 675 | `$0.008` | `$5.40` |
| VOC | 225 | `$0.003` | `$0.68` |
| 합계 | 4,500 | - | `$54.68/월` |

운영 중 FAQ retry 비율과 bug precheck 비중이 높아지면 총액은 대략 `$60~75/월` 구간으로 올라갈 수 있다.

### 보수적 상한 시나리오

FAQ 위주 유입과 retry 증가를 반영한 상한 가정:

- FAQ `$0.025/건`
- Payment `$0.008/건`
- Bug `$0.010/건`
- VOC `$0.004/건`

동일 분포 60/20/15/5 적용 시:

| 문의 유형 | 월 건수 | 1건 평균 비용 | 월 비용 |
| --- | ---: | ---: | ---: |
| FAQ | 2,700 | `$0.025` | `$67.50` |
| Payment | 900 | `$0.008` | `$7.20` |
| Bug | 675 | `$0.010` | `$6.75` |
| VOC | 225 | `$0.004` | `$0.90` |
| 합계 | 4,500 | - | `$82.35/월` |

### `chatbot` 최종 추정

- 낙관적 평균: `$55 내외/월`
- 일반 운영 추정: `$60~75/월`
- 보수적 상한: `$80대/월`

## 4. 비교 요약

| 시스템 | 월 비용 추정 | 특징 |
| --- | ---: | --- |
| `cs_auto` | `$121.33/월` | 분석과 답변 생성, 주간 리포트까지 포함한 배치형 비용 |
| `chatbot` | `$60~75/월` | FAQ 비중과 retry 빈도에 민감한 실시간 유형별 비용 |

핵심 해석:

- 현재 추정 기준에서는 `cs_auto`가 `chatbot`보다 비싸다.
- `cs_auto`는 `answer_agent` 중심 비용 구조다.
- `chatbot`은 FAQ 비중이 높아질수록 비용이 빠르게 올라간다.
- 두 시스템 모두 모델 교체, retrieval 호출 수 감소, retry 축소가 가장 직접적인 비용 절감 수단이다.

## 5. 주의사항

### `cs_auto` 배치 제한

현재 기본값이면 하루 150건을 한 번의 일배치로 모두 처리하지 못할 수 있다.

- analysis default limit: `50`
- answer default limit: `50`

근거:

- [apps/cs_auto/backend/agents/analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/analysis_agent.py:440)
- [apps/cs_auto/backend/agents/answer_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/answer_agent.py:231)

따라서 `cs_auto` 월 비용은 아래 중 하나를 전제로 한다.

1. `CS_AUTO_ANALYSIS_BATCH_LIMIT`, `CS_AUTO_ANSWER_BATCH_LIMIT`를 150 이상으로 조정
2. 하루 여러 번 DAG 실행
3. backlog를 허용하되 월 전체 4,500건을 결국 모두 처리

### 실제 비용이 달라질 수 있는 요인

- `payment`, `gacha` 비중 증가 시 `text-to-sql` 비용 증가
- `DB&DOC` 비중 증가 시 `cs_auto` 평균 단가 상승
- FAQ retry, rerank, rewrite 발생률 증가 시 `chatbot` 비용 상승
- 문서 retrieval query 길이 증가 시 생성 및 rerank 비용 상승
- `gpt-4o-mini` 등 저가 모델로 교체 시 비용 급감 가능
- moderation 실제 청구 기준 반영 시 `chatbot` 총액 변동 가능

## 6. 한 줄 결론

- `cs_auto`는 현재 구조 기준 `약 $121/월`, `chatbot`은 일반 운영 기준 `약 $60~75/월`로 보는 것이 가장 현실적이다.
