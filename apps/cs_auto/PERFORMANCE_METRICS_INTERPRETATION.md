# `analysis_agent` / `answer_agent` 성능 평가 지표 해석

## 목적

이 문서는 `apps/cs_auto`의 두 핵심 에이전트에 대해, 현재 저장소에 있는 코드와 평가 데이터셋 구조를 기준으로 성능 지표를 어떻게 해석해야 하는지 정리한 문서다.

- `analysis_agent`: 문의를 분류하고 `routing_target`을 정하는 1차 분석 단계
- `answer_agent`: 근거를 수집하고 답변 초안을 생성한 뒤 안전성 점수로 최종 초안을 결정하는 단계

기준이 되는 구현/데이터셋:

- [analysis_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/analysis_agent.py)
- [answer_agent.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/agents/answer_agent.py)
- [routing_target_gold_dataset_live_samples.json](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/evals/routing_target_gold_dataset_live_samples.json)
- [answer_agent_eval_dataset_live.json](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/evals/answer_agent_eval_dataset_live.json)

## 실제 수치 요약

현재 저장소에는 모델을 실행해 산출한 `Accuracy`, `F1`, `BLEU` 같은 최종 점수표는 없다. 대신 실제로 확인 가능한 수치는 아래 3종류다.

- 평가 데이터셋의 실제 표본 수와 분포
- 운영 DB 기준 `routing_target` 실분포
- `answer_agent` 안전성 점수의 계산식과 승인 임계값

즉, 지금 문서에서 “실제 나와 있는 수치”는 모델 결과 리더보드가 아니라, 평가 설계와 운영 난이도를 보여주는 숫자라고 보는 게 정확하다.

## 0. 제일 이야기거리 있는 실제 수치

가장 해석 가치가 큰 숫자는 `answer_agent_eval_dataset_live.json` 안의 “운영 분포 대비 평가셋 분포”다.

### 표 1. 운영 분포 vs 답변 평가셋 분포

| routing_target | 운영 DB 분포 수 | 운영 비중 | 답변 평가셋 수 | 평가셋 비중 | 평가셋/운영 배율 |
|---|---:|---:|---:|---:|---:|
| `doc_only` | 172 | 68.8% | 23 | 35.9% | 0.52x |
| `DB_only` | 35 | 14.0% | 15 | 23.4% | 1.67x |
| `DB&DOC` | 21 | 8.4% | 13 | 20.3% | 2.42x |
| `fixed_answer` | 22 | 8.8% | 13 | 20.3% | 2.31x |
| `total` | 250 | 100.0% | 64 | 100.0% | - |

### 해석

이 표가 가장 흥미로운 이유는 평가셋이 운영 트래픽을 그대로 복제하지 않고, 어려운 케이스를 의도적으로 증폭하고 있기 때문이다.

- `doc_only`는 운영에서 68.8%로 절대 다수지만, 평가셋에서는 35.9%까지 낮췄다.
- 반대로 `DB&DOC`는 운영에서 8.4%밖에 안 되는데 평가셋에서는 20.3%까지 끌어올렸다.
- `fixed_answer`도 운영 8.8%에서 평가셋 20.3%로 크게 늘렸다.
- `DB_only` 역시 운영 14.0%에서 평가셋 23.4%로 확대됐다.

이건 좋은 평가 설계다. 이유는 운영에서 많이 들어오는 쉬운 문의보다, 자동화 사고가 나기 쉬운 어려운 문의를 더 강하게 검증하고 있기 때문이다.

실무적으로는 아래처럼 읽으면 된다.

- `doc_only` 성능만 좋게 나와도 전체 체감 품질은 괜찮아 보일 수 있다.
- 하지만 실제 리스크는 `DB_only`, `DB&DOC`, `fixed_answer`에서 더 크게 난다.
- 그래서 이 평가셋은 “평균 점수 잘 나오는 모델”보다 “위험 케이스를 덜 틀리는 모델”을 고르기 좋다.

즉, 이 프로젝트의 평가는 “쉬운 문제 많이 맞히기”보다 “까다로운 문제에서 사고 덜 내기” 쪽으로 설계돼 있다.

## 0-1. 평가셋이 실제로 어디에 초점을 두는가

### 표 2. `answer_agent` 평가셋의 `eval_focus` 분포

| eval_focus | 건수 | 비중 |
|---|---:|---:|
| `document_retrieval` | 23 | 35.9% |
| `policy_grounding` | 23 | 35.9% |
| `no_db_claims` | 23 | 35.9% |
| `db_retrieval` | 15 | 23.4% |
| `factual_grounding` | 15 | 23.4% |
| `no_policy_hallucination` | 15 | 23.4% |
| `hybrid_retrieval` | 13 | 20.3% |
| `conflict_resolution` | 13 | 20.3% |
| `policy_plus_state` | 13 | 20.3% |

### 해석

이 수치도 이야기거리가 크다.

- `doc_only` 구간은 단순 문서 검색만 보는 게 아니라 `policy_grounding`, `no_db_claims`까지 같이 본다.
- 즉 “문서를 잘 찾았는가”보다 “문서형 문의에 DB 상태를 멋대로 섞지 않았는가”를 같이 체크한다.
- `DB_only` 구간은 `db_retrieval`뿐 아니라 `no_policy_hallucination`을 본다.
- 즉 실제 상태를 읽는 모델이어도 정책을 임의로 덧붙이면 감점 대상이라는 뜻이다.
- `DB&DOC` 구간은 `hybrid_retrieval`, `conflict_resolution`, `policy_plus_state`를 본다.
- 즉 이 프로젝트에서 가장 어려운 클래스는 단순 검색이 아니라 “상태와 정책을 동시에 모순 없이 설명하는 능력”이다.

한 줄로 요약하면, 이 평가셋은 검색 정확도보다 “근거 경계선 지키기”를 더 엄격하게 본다.

## 0-2. 답변 평가셋의 카테고리 구성

### 표 3. `answer_agent` 평가셋 카테고리 분포

| category | 건수 | 비중 |
|---|---:|---:|
| `bug` | 33 | 51.6% |
| `account` | 16 | 25.0% |
| `general` | 10 | 15.6% |
| `payment` | 3 | 4.7% |
| `refund` | 2 | 3.1% |
| `total` | 64 | 100.0% |

### 해석

이 표는 처음 보면 의외다. `answer_agent` 평가셋은 `payment`나 `refund`보다 `bug`가 훨씬 많다.

이걸 이렇게 해석할 수 있다.

- 이 시스템에서 `bug` 문의가 단순 기술문의가 아니라, 문서 안내와 상태 확인 경계가 자주 섞이는 주요 자동화 대상일 가능성이 크다.
- `account`가 25.0%로 큰 비중을 차지하는 것도 의미가 있다.
- 계정류 문의는 운영상 민감하고, `DB_only` 또는 `fixed_answer`로 갈 가능성이 있어 안전성 관리 가치가 높다.
- 반대로 `payment`, `refund` 비중은 낮다.
- 따라서 이 평가셋은 “결제/환불 특화 에이전트”보다는 “문서/계정/혼합형 CS 전반”을 검증하는 성격이 더 강하다.

즉, 현재 `answer_agent`는 금융성 예외 처리보다, 일반 CS 대화에서 환각 없이 근거를 맞추는 능력을 더 강하게 테스트받고 있다.

## 0-3. `analysis_agent`용 골드 후보셋 분포

`analysis_agent`는 최종 점수표보다 골드 후보셋 구성이 더 직접적인 수치다.

### 표 4. `routing_target` 골드 후보셋 분포

| routing_target | 건수 | 비중 |
|---|---:|---:|
| `doc_only` | 4 | 16.0% |
| `DB_only` | 12 | 48.0% |
| `DB&DOC` | 9 | 36.0% |
| `total` | 25 | 100.0% |

### 해석

이 후보셋은 `doc_only`보다 `DB_only`, `DB&DOC`가 훨씬 많다.

- `DB_only + DB&DOC`가 84.0%다.
- 즉 `analysis_agent` 평가 준비는 “어떤 근거를 봐야 하는지 헷갈리기 쉬운 문의” 중심으로 짜여 있다.
- 특히 `DB&DOC`가 36.0%라는 건 운영상 가장 틀리기 쉬운 혼합형 라우팅을 중요 문제로 보고 있다는 신호다.

좋게 말하면 평가가 공격적이고, 나쁘게 말하면 이 라우팅 단계가 아직 가장 불안한 병목일 가능성이 있다.

## 0-4. `answer_agent` 안전성 승인 기준

`answer_agent` 코드에는 실제 승인 수치 기준이 하드코딩되어 있다.

### 표 5. 안전성 승인 로직의 실제 수치

| 항목 | 실제 값 | 의미 |
|---|---:|---|
| `SAFETY_APPROVAL_THRESHOLD` | 0.7 | 평균 안전성 점수가 0.7을 초과해야 초안 유지 |
| `hallucination_score` 가중 방향 | `1 - score` | 환각 점수는 낮을수록 유리 |
| `toxicity_score` 가중 방향 | `1 - score` | 독성 점수는 낮을수록 유리 |
| `policy_violation_score` 가중 방향 | `1 - score` | 정책 위반 점수는 낮을수록 유리 |
| `factuality_score` 가중 방향 | `score` | 사실성 점수는 높을수록 유리 |
| 평균 계산 항목 수 | 4 | 네 축 평균으로 승인 여부 결정 |

평균식:

```text
average_score =
((1 - hallucination_score)
+ (1 - toxicity_score)
+ (1 - policy_violation_score)
+ factuality_score) / 4
```

### 해석

이 수치도 꽤 이야기거리가 있다.

- 기준이 `>= 0.7`이 아니라 `> 0.7`이다.
- 즉 평균이 정확히 `0.7000`이면 승인되지 않는다.
- 안전성 4축을 완전히 동일 가중치로 평균낸다.
- 따라서 환각 1건이 매우 치명적인 도메인이라면, 현재 식은 다소 “평균주의”다.
- 반대로 일반 CS 자동화에서는 구현이 단순하고 운영 해석이 쉽다는 장점이 있다.

이 로직이 뜻하는 운영 철학은 명확하다.

- 잘 쓴 답변보다, 안전한 답변을 우선한다.
- 점수가 애매하면 생성 답변을 살리지 않고 `fixed_answer`로 내린다.

따라서 이후 실제 실험 수치가 들어오면, 가장 먼저 볼 숫자는 단순 문장 품질이 아니라 아래 두 개다.

- `approved` 비율이 너무 낮지 않은가
- 그런데도 `must_not_include` 위반이 여전히 남아 있지 않은가

## 1. `analysis_agent` 지표 해석

### 1-1. 이 에이전트가 잘해야 하는 일

`analysis_agent`는 문의 1건에 대해 아래 값을 만든다.

- `category`
- `sentiment`
- `risk_level`
- `routing_target`
- `summary`

이 중 운영 영향도가 가장 큰 값은 `routing_target`이다. 이유는 이 값이 이후 `answer_agent`가 어떤 근거를 찾을지 직접 결정하기 때문이다.

- `doc_only`: 문서/공지/정책 중심으로 답해야 하는 문의
- `DB_only`: 결제, 환불, 계정 상태처럼 개인 상태 조회가 필요한 문의
- `DB&DOC`: 개인 상태와 정책 안내를 함께 봐야 하는 문의
- `fixed_answer`: 검색 근거 없이 고정 안내문 또는 보수적 응답으로 가야 하는 문의

### 1-2. 가장 중요한 지표

#### `routing_target` 정확도 (`Accuracy`)

가장 먼저 봐야 하는 지표다.

- 높을수록: 올바른 근거 경로로 후속 답변 생성이 이어진다.
- 낮을수록: 답변 품질이 구조적으로 무너진다. 이후 LLM이 잘 써도 근거가 틀리면 초안이 흔들린다.

실무 해석:

- `doc_only`를 `DB_only`로 보내면: 공지/정책성 문의에 개인 상태 추정이 섞일 수 있다.
- `DB_only`를 `doc_only`로 보내면: 실제 결제/환불/배송 상태를 확인하지 못해 고객 상황과 어긋난 답변이 나온다.
- `DB&DOC`를 다른 클래스로 보내면: “내 상태 + 정책 조건”을 동시에 설명해야 하는 문의가 반쪽짜리 답변이 된다.
- `fixed_answer`를 놓치면: 근거 부족 상황인데도 과도하게 구체적인 답변을 생성할 위험이 생긴다.

#### 클래스별 `Precision / Recall / F1`

전체 정확도만 보면 데이터가 많은 클래스가 결과를 가려버릴 수 있다. 그래서 `routing_target`은 클래스별로 같이 봐야 한다.

`Recall` 해석:

- `doc_only Recall`이 낮다: 공지/FAQ형 문의를 자주 다른 경로로 보낸다는 뜻
- `DB_only Recall`이 낮다: 고객 개인 상태 확인이 필요한 문의를 자주 놓친다는 뜻
- `DB&DOC Recall`이 낮다: 가장 어려운 혼합형 문의를 제대로 못 잡는다는 뜻
- `fixed_answer Recall`이 낮다: 보수적으로 막아야 할 문의를 초안 생성 경로로 흘린다는 뜻

`Precision` 해석:

- `doc_only Precision`이 낮다: 문서만 보면 안 되는 문의까지 문서형으로 과분류하고 있다
- `DB_only Precision`이 낮다: 개인 DB 조회가 불필요한 문의에도 DB 경로를 남발하고 있다
- `DB&DOC Precision`이 낮다: 혼합형을 과하게 예측해 시스템이 복잡해지고 답변이 장황해질 수 있다
- `fixed_answer Precision`이 낮다: 답할 수 있는 문의도 너무 쉽게 보수 응답으로 보내고 있다

`F1` 해석:

- Precision과 Recall을 같이 반영한 균형 지표다.
- 클래스별 운영 품질을 한 번에 보려면 `F1`이 가장 읽기 쉽다.

#### `Macro F1`과 `Weighted F1`

- `Macro F1`: 모든 클래스를 동등하게 본다. 소수 클래스인 `DB&DOC`, `fixed_answer`를 놓치지 않는지 보기 좋다.
- `Weighted F1`: 실제 데이터 비중을 반영한다. 운영 전체 평균 체감 품질에 가깝다.

해석 원칙:

- `Weighted F1`만 높고 `Macro F1`이 낮으면, 흔한 문의는 잘 처리하지만 어려운 예외 케이스를 놓치고 있을 가능성이 크다.
- `Macro F1`이 안정적이면 라우팅 정책이 전반적으로 균형 잡혀 있다는 뜻이다.

### 1-3. 보조 지표

#### `category` 분류 정확도

`category`는 직접 답변을 만들지는 않지만, `risk_level`과 `routing_signals`, 이후 검색 방향에 영향을 준다.

- 높을수록: 문의 의미를 안정적으로 파악한다.
- 낮을수록: 라우팅이 연쇄적으로 흔들릴 수 있다.

특히 `payment`, `refund`, `account`는 코드상 `risk_level = MID`에 직접 연결되므로 오분류 비용이 크다.

#### `risk_level` 정확도

- 낮게 잡으면: 위험 문의를 일반 문의처럼 취급할 수 있다.
- 높게 잡으면: 운영팀이 불필요하게 긴장하거나 보수적으로 처리할 수 있다.

이 지표는 “정답과의 일치”보다 “고위험 누락이 얼마나 적은가”를 더 중요하게 봐야 한다.

즉, `HIGH Recall`이 핵심이다.

#### `sentiment` 정확도

운영상 우선순위는 상대적으로 낮다.

- 높을수록: 고객 톤 분석이 안정적이다.
- 낮더라도: 라우팅과 근거 검색이 맞으면 답변 품질에 미치는 영향은 제한적이다.

### 1-4. 오차 패턴 해석

혼동행렬을 볼 때는 단순히 “틀렸다”보다 어느 방향으로 틀리는지 봐야 한다.

- `DB_only -> doc_only` 오분류가 많다: 개인 상태 확인 누락 위험
- `doc_only -> DB_only` 오분류가 많다: 근거 없는 개인 상태 추정 위험
- `DB&DOC -> DB_only` 오분류가 많다: 정책 단서가 빠진 답변 증가
- `DB&DOC -> doc_only` 오분류가 많다: 실제 상태 확인 없는 일반론 답변 증가
- `* -> fixed_answer` 오분류가 많다: 지나치게 보수적이라 자동화 효율이 떨어짐
- `fixed_answer -> *` 오분류가 많다: 안전해야 할 케이스에서 환각 위험 증가

### 1-5. `analysis_agent`에서 우선순위가 높은 지표 순서

1. `routing_target` 클래스별 Recall, 특히 `DB_only`, `DB&DOC`, `fixed_answer`
2. `routing_target` Macro F1
3. `routing_target` 전체 Accuracy
4. `category` Accuracy / F1
5. `risk_level`의 고위험 Recall
6. `sentiment` Accuracy

## 2. `answer_agent` 지표 해석

### 2-1. 이 에이전트가 잘해야 하는 일

`answer_agent`는 아래 흐름으로 동작한다.

1. `routing_target`에 따라 근거 수집
2. 초안 생성
3. 안전성 평가
4. 안전하면 초안 유지, 아니면 `fixed_answer`로 대체

즉, 이 에이전트 평가는 단순 생성 품질이 아니라 아래 3개를 함께 봐야 한다.

- 근거를 제대로 찾았는가
- 초안이 근거에 맞는가
- 안전하지 않으면 보수적으로 차단했는가

### 2-2. 가장 중요한 지표

#### `must_include` 충족률

평가 데이터셋에는 각 예시마다 “반드시 들어가야 하는 정보”가 있다.

- 높을수록: 고객이 꼭 알아야 할 핵심 사실이나 정책을 빠뜨리지 않았다.
- 낮을수록: 답변이 그럴듯해도 실질적으로는 불완전하다.

해석 예시:

- `doc_only`에서 낮다: 공지 제목, 정책 조건, 안내 경로를 놓친다.
- `DB_only`에서 낮다: 실제 결제 상태, 환불 상태, 배송 상태를 설명하지 못한다.
- `DB&DOC`에서 낮다: 개인 상태와 정책 조건 중 한쪽만 답한다.
- `fixed_answer`에서 낮다: 고정 안내문이 필요한 보수 응답을 제대로 유지하지 못한다.

#### `must_not_include` 위반률

데이터셋에는 “절대 들어가면 안 되는 정보”도 정의되어 있다.

- 낮을수록 좋다.
- 높을수록: 근거 없는 추정, 과도한 확답, 허위 상태 설명이 많다는 뜻이다.

이 지표는 특히 환각과 직접 연결된다.

예시:

- 존재하지 않는 환불 진행 상태를 만들어냄
- 문서에 없는 보상/예외 처리를 단정함
- DB에 없는 결제 실패/성공 상태를 추정함

#### 근거 일치율 (`evidence hit rate`)

평가 데이터셋에는 gold 문서 또는 gold DB 사실이 있다. 생성 답변이 그 gold 근거를 실제로 사용했는지 보는 지표다.

- 높을수록: retrieval과 generation이 연결되어 있다.
- 낮을수록: 검색은 했지만 초안이 다른 방향으로 쓴다는 뜻이다.

이 지표는 아래처럼 나눠 보면 좋다.

- gold 문서 포함률
- gold DB 사실 반영률
- 혼합형(`DB&DOC`)에서 양쪽 근거 동시 반영률

### 2-3. 안전성 점수 해석

`answer_agent`는 초안 생성 뒤 아래 점수를 산출한다.

- `hallucination_score`
- `toxicity_score`
- `policy_violation_score`
- `factuality_score`
- `average_score`
- `safety_action`

코드 기준 평균 점수 계산식은 아래와 같다.

```text
average_score =
((1 - hallucination_score)
+ (1 - toxicity_score)
+ (1 - policy_violation_score)
+ factuality_score) / 4
```

승인 기준:

- `average_score > 0.7` 이면 `approved`
- 그 이하면 `fixed_answer`

#### `hallucination_score`

- 낮을수록 좋다.
- 높으면: 검색 근거에 없는 결론, 상태 추정, 예외 처리 생성 가능성이 크다.

운영상 가장 민감한 점수 중 하나다.

#### `toxicity_score`

- 낮을수록 좋다.
- 높으면: 고객 응대 문체가 공격적이거나 부적절할 수 있다.

일반 CS 환경에서는 보통 크게 튀지 않아야 정상이다. 이 값이 자주 높다면 프롬프트 톤 제어에 문제가 있다는 신호다.

#### `policy_violation_score`

- 낮을수록 좋다.
- 높으면: 내부 정책 또는 안전 가이드에 어긋나는 안내를 하고 있다는 뜻이다.

예를 들어 운영자가 확정하지 않은 보상, 수동 조치, 예외 승인 등을 AI가 단정하는 경우가 여기에 해당한다.

#### `factuality_score`

- 높을수록 좋다.
- 낮으면: 문장 자체는 자연스러워도 근거 충실도가 낮다는 뜻이다.

#### `average_score`

- 가장 쉽게 대시보드에서 볼 수 있는 종합 안전성 지표다.
- 다만 평균이기 때문에, 특정 한 축의 치명적인 문제를 가릴 수 있다.

해석 원칙:

- `average_score`가 높아도 `hallucination_score`가 높으면 위험하다.
- 따라서 평균만 보지 말고 4개 구성 점수를 같이 봐야 한다.

### 2-4. 라우팅 결과 지표 해석

#### `safety_action` 비율

- `approved` 비율이 높을수록: 초안이 그대로 사용 가능한 경우가 많다.
- `fixed_answer` 비율이 높을수록: 안전성 필터가 많이 개입한다.

하지만 이 비율은 단독 해석하면 안 된다.

- `approved`가 너무 높다: 필터가 느슨할 수 있다.
- `fixed_answer`가 너무 높다: 생성 품질이 낮거나 필터가 과보수적일 수 있다.

적절한 해석은 아래 조합이다.

- `approved` 비율 + `must_not_include` 위반률
- `fixed_answer` 비율 + 실제 human approval rate

#### `safety_label`

최종 초안 기준 레이블이다.

- `safe`: 초안을 유지
- `review_required`: 고정 답변으로 교체되었거나 사람이 더 봐야 하는 상태

`review_required`가 많다는 것은 “자동화율”은 낮다는 뜻이지만, 동시에 안전장치가 제대로 작동한다는 뜻일 수도 있다.

### 2-5. 초안 품질 보조 지표

#### `used_evidence_count`

이 값은 “근거를 몇 개 썼는가”를 보여주는 보조 지표다.

- 너무 낮으면: 필요한 근거를 충분히 못 반영했을 가능성
- 너무 높으면: 답변이 장황하거나 관련성 낮은 근거까지 끌어왔을 가능성

중요한 점:

- 이 값이 높다고 좋은 답변은 아니다.
- “필요한 근거를 적절한 수만큼 썼는가”가 중요하다.

특히 `DB&DOC`에서 `used_evidence_count`가 낮으면서 품질도 낮다면, 혼합형 근거 조합이 약하다는 신호로 볼 수 있다.

#### `review_reason`

이 값은 왜 사람이 다시 봐야 하는지 보여준다.

해석 용도:

- 특정 사유가 반복되면 프롬프트 개선 대상
- 특정 라우팅 클래스에서만 반복되면 retrieval 또는 라우팅 문제가 원인일 수 있음

### 2-6. `answer_agent`에서 우선순위가 높은 지표 순서

1. `must_not_include` 위반률
2. `must_include` 충족률
3. gold 근거 일치율
4. `hallucination_score`와 `factuality_score`
5. `average_score`
6. `approved` / `fixed_answer` 비율
7. `used_evidence_count`

## 3. 두 에이전트를 함께 볼 때의 해석

두 에이전트는 독립이 아니라 직렬 구조다. 따라서 `answer_agent` 성능이 낮더라도 원인이 `analysis_agent`일 수 있다.

### 3-1. `analysis_agent`가 나쁘면 나타나는 현상

- `answer_agent`의 gold 근거 일치율이 낮아짐
- `must_include` 충족률이 떨어짐
- `must_not_include` 위반률이 올라감
- `fixed_answer` 비율이 비정상적으로 증가하거나 감소함

즉, 답변 생성 품질 문제처럼 보여도 실제 원인은 잘못된 `routing_target`일 수 있다.

### 3-2. 운영에서 가장 위험한 조합

가장 위험한 실패는 아래 조합이다.

1. `analysis_agent`가 `fixed_answer` 또는 `DB&DOC`를 놓침
2. `answer_agent`가 부족한 근거로 초안을 생성함
3. safety 점수도 통과해 `approved`됨

이 경우 잘못된 답변이 자동 초안으로 저장되므로, 단순 정확도보다 “위험 클래스 Recall”과 “환각 억제 지표”를 우선시해야 한다.

## 4. 실무용 해석 요약

### `analysis_agent`

- 제일 중요한 것은 `routing_target` 성능이다.
- 전체 Accuracy보다 클래스별 Recall과 Macro F1이 더 중요하다.
- 특히 `DB_only`, `DB&DOC`, `fixed_answer`를 놓치면 운영 리스크가 크다.

### `answer_agent`

- 제일 중요한 것은 “없는 사실을 쓰지 않는가”다.
- 그래서 `must_not_include` 위반률, `hallucination_score`, `factuality_score`를 먼저 본다.
- 그 다음에 `must_include` 충족률과 gold 근거 반영률을 본다.
- `average_score`는 편한 요약값이지만, 단독 판단 기준으로 쓰면 안 된다.

### 최종 우선순위

1. `analysis_agent`의 `routing_target` 위험 클래스 Recall
2. `answer_agent`의 `must_not_include` 위반률
3. `answer_agent`의 gold 근거 반영률
4. `answer_agent`의 `must_include` 충족률
5. `answer_agent`의 safety 세부 점수

## 5. 권장 보고 형식

주간/실험 비교 보고서는 아래 형태가 가장 읽기 쉽다.

### `analysis_agent`

- `routing_target Accuracy`
- `routing_target Macro F1`
- 클래스별 `Precision / Recall / F1`
- `category Accuracy`
- `risk_level HIGH Recall`
- 혼동행렬

### `answer_agent`

- `must_include` 충족률
- `must_not_include` 위반률
- gold 문서/DB 근거 일치율
- `hallucination_score`, `policy_violation_score`, `factuality_score`
- `average_score`
- `approved` 비율, `fixed_answer` 비율

이 형식으로 보면 “분석이 틀렸는지”, “검색이 약한지”, “초안 생성이 환각을 내는지”, “안전성 필터가 과하거나 부족한지”를 분리해서 해석할 수 있다.
