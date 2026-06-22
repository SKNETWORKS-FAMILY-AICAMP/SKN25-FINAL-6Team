# CS Auto 평가 및 성능 요약

## 문서 목적

이 문서는 `analysis_agent`와 `answer_agent`의 성능지표, 실제 평가 결과, 평가셋 구성 방식을 한 곳에 정리한 통합 요약본이다.

- 운영 대시보드에서 지속적으로 봐야 하는 KPI
- 최신 평가 산출물 기준 핵심 성능 수치
- 발표용 해석 포인트
- 평가 데이터셋 생성 방식과 분포

## 기준 산출물

### 실제 평가 결과

- [analysis accuracy_summary.csv](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/accuracy_summary.csv)
- [analysis confusion_matrix.md](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/confusion_matrix.md)
- [analysis report.json](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/report.json)
- [answer report 2026-06-18 16:19:07](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260618_161907/answer_agent/report.json)
- [answer report 2026-06-22 06:39:53](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260622_063953/answer_agent/report.json)

### 평가 데이터셋 및 코드

- [answer_agent_eval_dataset_live.json](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/evals/answer_agent_eval_dataset_live.json)
- [routing_target_gold_dataset_live_candidates.json](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/evals/routing_target_gold_dataset_live_candidates.json)
- [test_analysis_agent_eval.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/test_analysis_agent_eval.py)
- [test_answer_agent_eval.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/test_answer_agent_eval.py)

## 1. 한 장 요약

- `analysis_agent`는 전반적으로 안정적이지만 핵심 병목은 `routing_target` 분류다.
- `analysis_agent`의 가장 큰 강점은 `fixed_answer Recall 100.00%`이고, 가장 큰 약점은 `DB_only Recall 69.23%`다.
- `answer_agent`는 라우팅과 실행 안정성은 높지만 평가셋이 커질수록 문서 retrieval 정밀도가 떨어진다.
- 현재 단계의 핵심 메시지는 "`answer_agent`의 병목은 orchestration이 아니라 retrieval precision"이다.

## 2. 운영 성능지표 체계

### 핵심 KPI

| 구분 | 핵심 지표 | 의미 |
| --- | --- | --- |
| 문의 처리량 | 전체 문의 수, 대기 문의 수, 종료 문의 수, 오늘 접수 수 | 유입량과 backlog 파악 |
| 처리 커버리지 | 분석 커버리지, 초안 커버리지, 응답률 | 자동화 파이프라인 실효성 확인 |
| 처리 속도 | 평균 응답 시간 | 운영 SLA 체감 지표 |
| 분포 지표 | 채널별 분포, 상태 분포, 라우팅 분포 | 문의 유형과 병목 위치 파악 |
| 리스크 | `risk_level` 분포, HIGH 문의 수 | 고위험 문의 탐지 |
| 품질 | 근거 첨부율, 평균 근거 관련도, 최종 응답률 | RAG 및 답변 품질 점검 |
| Safety | hallucination, toxicity, policy violation, factuality 평균 | 생성 안전성과 정확성 점검 |
| 예외 처리 | human review 대상 수, 긴급 알림 수, 장기 미처리 문의 수 | 자동화 실패와 운영 개입 구간 파악 |

### 권장 임계치

| 항목 | 경고 기준 |
| --- | --- |
| 평균 hallucination score | `>= 0.7` |
| 평균 toxicity score | `>= 0.7` |
| 평균 policy violation score | `>= 0.7` |
| 평균 factuality score | `<= 0.3` |
| 응답률 | `< 0.7` |
| 초안 커버리지 | `< 0.7` |
| 근거 첨부율 | `< 0.8` |
| 장기 대기 문의 수 | `>= 10` |

### 운영 해석 포인트

- 단순 문의량보다 `응답률`, `초안 커버리지`, `human_review 비율`을 함께 봐야 자동화 실효성을 판단할 수 있다.
- Safety 평균 점수만 보면 위험이 가려질 수 있으므로 개별 지표와 임계치 초과 건수를 같이 봐야 한다.
- `routing_target` 분포가 급변하면 retrieval 경로 선택 문제가 생겼을 가능성이 높다.
- `pending backlog`, `human_review queue`, `negative sentiment`는 스파이크 기반 경보로 보는 것이 실용적이다.

## 3. `analysis_agent` 평가 결과

### 평가 범위

`analysis_agent`는 문의 1건에 대해 `category`, `risk_level`, `sentiment`, `routing_target` 4개 축을 예측한다. 이 중 운영적으로 가장 중요한 축은 이후 근거 경로를 직접 결정하는 `routing_target`이다.

### 축별 정확도

기준 실행 시각은 `2026-06-16 17:08:39`이다.

| 축 | 정답 수 | 전체 수 | 정확도 |
| --- | ---: | ---: | ---: |
| `risk_level` | 132 | 143 | 92.31% |
| `category` | 126 | 143 | 88.11% |
| `routing_target` | 117 | 143 | 81.82% |
| `sentiment` | 111 | 143 | 77.62% |

### `routing_target` 클래스별 성능

| 클래스 | Gold | Predicted | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fixed_answer` | 20 | 23 | 86.96% | 100.00% | 93.02% |
| `doc_only` | 57 | 57 | 84.21% | 84.21% | 84.21% |
| `DB_only` | 39 | 30 | 90.00% | 69.23% | 78.26% |
| `DB&DOC` | 27 | 33 | 66.67% | 81.48% | 73.33% |

### 대표 오분류

| Gold | Predicted | Count | 의미 |
| --- | --- | ---: | --- |
| `DB_only` | `DB&DOC` | 6 | 개인 상태 문의를 혼합형으로 과상향 |
| `doc_only` | `DB&DOC` | 5 | 문서형 문의에도 상태/정책 해석이 과하게 섞임 |
| `DB&DOC` | `doc_only` | 3 | 혼합형 일부를 단순 문서형으로 축소 |
| `fixed_answer` | other | 0 | fallback 차단은 안정적 |

### 해석

- 가장 안정적인 축은 `risk_level`이다.
- 가장 중요한 병목은 `routing_target`이다.
- `fixed_answer` recall 100%로 보수적 fallback은 강하다.
- 반대로 `DB_only`는 precision은 높지만 recall이 낮아 실제 DB-only 케이스를 놓치고 있다.
- `DB&DOC`는 precision이 가장 낮아 애매한 케이스를 hybrid로 과다 분류하는 경향이 있다.

## 4. `answer_agent` 평가 결과

### 평가 범위

현재 `answer_agent` 평가는 최종 자연어 답변의 완성도 전체를 채점하기보다 아래 3가지를 중심으로 본다.

- DB route decision accuracy
- SQL path execution success
- document retrieval hit rate

즉 이 결과는 "최종 답변 품질 점수"보다 "근거 경로 성능" 평가로 읽는 것이 맞다.

### 베스트 런 vs 최신 런

| 지표 | 2026-06-18 16:19:07 | 2026-06-22 06:39:53 | 해석 |
| --- | ---: | ---: | --- |
| 평가 티켓 수 | 25 | 64 | 최신 평가셋이 더 큼 |
| DB 케이스 수 | 21 | 28 | DB 범위 확대 |
| 문서 케이스 수 | 13 | 36 | 문서 평가 범위 확대 |
| DB router 정확도 | 100.00% | 96.43% | 여전히 매우 강함 |
| 문서 retrieval 실행 성공률 | 100.00% | 100.00% | 실행 안정성 유지 |
| Gold document hit | 100.00% | 61.11% | 큰 셋에서 정밀도 하락 |
| Gold chunk hit | 100.00% | 55.56% | exact grounding 정밀도 하락 |

### 성능 변화 추이

| 실행 시각 | DB router 정확도 | Gold document hit | Gold chunk hit | 해석 |
| --- | ---: | ---: | ---: | --- |
| 2026-06-18 15:50:29 | 47.62% | 0/13 | 0/13 | 초기 상태, 라우팅과 검색 모두 약함 |
| 2026-06-18 15:56:59 | 100.00% | 0/13 | 0/13 | 라우터 먼저 개선 |
| 2026-06-18 16:06:34 | 100.00% | 5/13 | 5/13 | retrieval 개선 시작 |
| 2026-06-18 16:19:07 | 100.00% | 13/13 | 13/13 | 소규모 셋 완전 적중 |
| 2026-06-22 06:39:53 | 96.43% | 22/36 | 20/36 | 대규모 셋에서 일반화 한계 노출 |

### Safety 해석 원칙

`answer_agent`의 safety 판단은 아래 평균식에 기반한다.

```text
average_score =
((1 - hallucination_score)
+ (1 - toxicity_score)
+ (1 - policy_violation_score)
+ factuality_score) / 4
```

- `average_score > 0.7` 이면 `approved`
- 그 외는 `fixed_answer`

평균 점수만 높아도 개별 위험이 가려질 수 있으므로 `hallucination_score`, `policy_violation_score`, `factuality_score`는 따로 관리해야 한다.

### 해석

- 최신 `answer_agent`의 문제는 실행 실패가 아니라 retrieval precision이다.
- 작은 셋에서는 완벽했지만 큰 셋에서는 일반화 한계가 드러났다.
- 현재 병목은 orchestration이 아니라 정답 문서와 chunk를 안정적으로 맞히는 능력이다.

## 5. 평가 데이터셋 구성

### `analysis_agent` 평가셋 생성 방식

- 평가 코드는 [test_analysis_agent_eval.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/test_analysis_agent_eval.py)를 사용한다.
- 입력 데이터는 `data/tests/analysis_agents/analysis_eval_all_axes_10_each_20260616.csv`다.
- 사람이 붙인 gold label을 기준으로 `ticket_id` 중복 제거 후 사용한다.
- 각 티켓에 대해 `build_analysis_result()`를 실행하고 gold와 예측을 비교한다.
- 비교 축은 `category`, `risk_level`, `sentiment`, `routing_target` 4개다.

### `analysis_agent` 평가셋 분포

| 항목 | 값 |
| --- | --- |
| 총 티켓 수 | 143 |
| 채널 분포 | `naver_cafe` 143 |
| 비교 축 | `category`, `risk_level`, `sentiment`, `routing_target` |

| `routing_target` 클래스 | 건수 | 비중 |
| --- | ---: | ---: |
| `doc_only` | 57 | 39.9% |
| `DB_only` | 39 | 27.3% |
| `DB&DOC` | 27 | 18.9% |
| `fixed_answer` | 20 | 14.0% |

| `category` 클래스 | 건수 | 비중 |
| --- | ---: | ---: |
| `bug` | 39 | 27.3% |
| `general` | 32 | 22.4% |
| `account` | 22 | 15.4% |
| `payment` | 17 | 11.9% |
| `refund` | 12 | 8.4% |
| `policy` | 11 | 7.7% |
| `gacha` | 10 | 7.0% |

| 항목 | 클래스 | 건수 | 비중 |
| --- | --- | ---: | ---: |
| `risk_level` | `LOW` | 84 | 58.7% |
| `risk_level` | `MID` | 30 | 21.0% |
| `risk_level` | `HIGH` | 29 | 20.3% |
| `sentiment` | `neutral` | 82 | 57.3% |
| `sentiment` | `negative` | 55 | 38.5% |
| `sentiment` | `positive` | 6 | 4.2% |

해석:

- 한 채널(`naver_cafe`)에 집중된 수동 gold 셋이다.
- `routing_target`은 `doc_only`가 가장 많지만 나머지 클래스도 충분히 포함돼 라우팅 비교가 가능하다.
- `sentiment`는 `positive`가 매우 적어 class imbalance 영향을 고려해야 한다.

### `answer_agent` 평가셋 생성 방식

- 평가 코드는 [test_answer_agent_eval.py](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/test_answer_agent_eval.py)를 사용한다.
- 기본 입력 데이터는 [answer_agent_eval_dataset_live.json](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/evals/answer_agent_eval_dataset_live.json)이다.
- 이 데이터셋은 live DB에서 추출한 예시로 구성된다.
- 문서형 케이스는 gold 문서 ID와 chunk ID를 포함한다.
- DB형 케이스는 DB route와 SQL path 검증이 가능하게 구성한다.
- `fixed_answer` 예시도 포함해 fallback-only 동작을 평가한다.

### 운영 분포 vs `answer_agent` 평가셋 분포

| routing_target | 운영 DB 수 | 운영 비중 | 평가셋 수 | 평가셋 비중 |
| --- | ---: | ---: | ---: | ---: |
| `doc_only` | 172 | 68.8% | 23 | 35.9% |
| `DB_only` | 35 | 14.0% | 15 | 23.4% |
| `DB&DOC` | 21 | 8.4% | 13 | 20.3% |
| `fixed_answer` | 22 | 8.8% | 13 | 20.3% |
| `total` | 250 | 100.0% | 64 | 100.0% |

### `answer_agent` 평가셋 내부 분포

| 항목 | 클래스 | 건수 | 비중 |
| --- | --- | ---: | ---: |
| `routing_target` | `doc_only` | 23 | 35.9% |
| `routing_target` | `DB_only` | 15 | 23.4% |
| `routing_target` | `DB&DOC` | 13 | 20.3% |
| `routing_target` | `fixed_answer` | 13 | 20.3% |
| `category` | `bug` | 33 | 51.6% |
| `category` | `account` | 16 | 25.0% |
| `category` | `general` | 10 | 15.6% |
| `category` | `payment` | 3 | 4.7% |
| `category` | `refund` | 2 | 3.1% |

| eval_focus | 건수 | 비중 |
| --- | ---: | ---: |
| `document_retrieval` | 23 | 35.9% |
| `policy_grounding` | 23 | 35.9% |
| `no_db_claims` | 23 | 35.9% |
| `db_retrieval` | 15 | 23.4% |
| `factual_grounding` | 15 | 23.4% |
| `no_policy_hallucination` | 15 | 23.4% |
| `hybrid_retrieval` | 13 | 20.3% |
| `conflict_resolution` | 13 | 20.3% |
| `policy_plus_state` | 13 | 20.3% |

해석:

- 운영에서는 `doc_only`가 절대 다수지만 평가셋은 `DB_only`, `DB&DOC`, `fixed_answer`를 의도적으로 더 많이 담았다.
- 단순 평균보다 어려운 라우팅과 근거 조합 문제를 얼마나 버티는지 보기에 적합하다.
- 쉬운 케이스보다 운영 리스크가 큰 케이스를 더 강하게 검증하는 설계다.

## 6. 종합 결론

### 현재 상태 한 줄 요약

- `analysis_agent`: 전반적으로 안정적이지만 `routing_target`이 핵심 병목
- `answer_agent`: 실행 안정성과 DB 라우팅은 강하지만 문서 retrieval 정밀도가 확장 병목

### 실무 우선순위

1. `analysis_agent`의 `DB_only Recall` 개선
2. `analysis_agent`의 `DB&DOC` 과예측 감소
3. `answer_agent`의 Gold document/chunk hit rate 개선
4. Safety 평균보다 개별 위험 score 기반 모니터링 강화
5. 운영 대시보드에서 `응답률`, `근거 첨부율`, `human_review queue`, `pending backlog` 상시 추적

### 발표용 핵심 문장

- `analysis_agent`는 전반적으로 안정적이지만 실제 병목은 라우팅이다.
- `fixed_answer` recall 100%는 안전한 fallback 처리 측면의 강점이다.
- `answer_agent`는 실행 실패 문제가 아니라 검색 정밀도 문제가 핵심이다.
- 최근 성능 변화는 단순 회귀라기보다 소규모 평가셋에서의 성공이 대규모 커버리지로 완전히 일반화되지는 않았다는 신호다.

## 7. 원문 출처

- [metrics.md](/C:/SKN25-FINAL-6Team/docs/weekly_report/metrics.md)
- [PERFORMANCE_METRICS_INTERPRETATION.md](/C:/SKN25-FINAL-6Team/apps/cs_auto/PERFORMANCE_METRICS_INTERPRETATION.md)
- [PERFORMANCE_EVAL_RESULTS.md](/C:/SKN25-FINAL-6Team/apps/cs_auto/PERFORMANCE_EVAL_RESULTS.md)
- [analysis_agent_eval.md](/C:/SKN25-FINAL-6Team/docs/cs_auto/analysis_agent_eval.md)
