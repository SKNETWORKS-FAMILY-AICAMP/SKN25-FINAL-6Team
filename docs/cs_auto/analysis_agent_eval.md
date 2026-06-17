# Analysis Agent 평가 정리

이 문서는 `apps/tests/cs-auto_tests/eval` 기준으로 `analysis_agent`의 평가 데이터, 데이터 구축 방식, 성능 해석을 정리한 것이다.

## 1. 평가 대상과 실행 기준

- 평가 스크립트: `apps/tests/cs-auto_tests/eval/test_analysis_agent_eval.py`
- 평가 함수: `agent.build_analysis_result(payload)`
- 평가 축:
  - `category`
  - `risk_level`
  - `sentiment`
  - `routing_target`
- 기본 평가 데이터셋:
  - `data/tests/analysis_agents/analysis_eval_all_axes_10_each_20260616.csv`

평가 스크립트는 CSV를 읽은 뒤 `ticket_id` 기준으로 중복을 제거하고, 각 티켓에 대해 gold label과 예측 label을 4개 축에서 각각 비교한다.

## 2. 사용 데이터

### 데이터 파일

- 합본 평가셋: `data/tests/analysis_agents/analysis_eval_all_axes_10_each_20260616.csv`
- 축별 파생 평가셋:
  - `analysis_eval_category_10_each_20260616.csv`
  - `analysis_eval_risk_10_each_20260616.csv`
  - `analysis_eval_sentiment_10_each_20260616.csv`
  - `analysis_eval_routing_10_each_20260616.csv`
- 수동 라벨링 샘플:
  - `analysis_eval_label_sample_20260616.csv`
- 수동 재라벨 스크립트:
  - `manual_relabel_analysis_eval_sets.py`

### 데이터 스키마

합본 CSV는 아래 컬럼을 사용한다.

- `focus_axis`
- `focus_case`
- `ticket_id`
- `title`
- `raw_query`
- `source_type`
- `gold_category`
- `gold_risk_level`
- `gold_sentiment`
- `gold_routing_target`
- `review_status`

### 데이터 규모

원본 합본 CSV는 총 `170`행이다.

- `category`: 7개 클래스 x 10건 = `70`행
- `risk`: 3개 클래스 x 10건 = `30`행
- `sentiment`: 3개 클래스 x 10건 = `30`행
- `routing`: 4개 클래스 x 10건 = `40`행

합계는 `170`행이지만, 평가 스크립트는 `ticket_id` 중복을 제거한다. 따라서 실제 평가에 들어간 샘플 수는 `143`건이다.

- 중복 제거 전: `170`행
- 중복 제거 후: `143`건
- 중복 행 수: `27`

중복 제거 방식은 `_load_eval_tickets()`에서 `deduped.setdefault(row["ticket_id"], row)`를 사용하는 형태라서, 같은 `ticket_id`가 여러 축에 등장하더라도 CSV에서 먼저 나온 1건만 최종 평가에 사용된다.

### 데이터 분포 특징

- `source_type`은 전부 `naver_cafe`다.
- `review_status`는 전부 `manual_checked`다.

중복 제거 후가 아니라 원본 170행 기준 라벨 분포는 아래와 같다.

- `gold_category`
  - `bug`: 49
  - `general`: 35
  - `account`: 29
  - `payment`: 22
  - `policy`: 12
  - `refund`: 12
  - `gacha`: 11
- `gold_risk_level`
  - `LOW`: 97
  - `MID`: 37
  - `HIGH`: 36
- `gold_sentiment`
  - `neutral`: 89
  - `negative`: 74
  - `positive`: 7
- `gold_routing_target`
  - `doc_only`: 70
  - `DB_only`: 46
  - `DB&DOC`: 34
  - `fixed_answer`: 20

즉, 축별 샘플링은 균형적으로 시작했지만 합본 후 중복 제거를 거치면서 최종 평가셋은 완전 균형 분포가 아니다.

## 3. 데이터 구축 방법

현재 저장소에서 확인 가능한 구축 과정은 아래 순서다.

### 1. 축별 10건 샘플 구성

파일명 자체가 축별 샘플링 기준을 드러낸다.

- `category`: 클래스별 10건
- `risk`: 클래스별 10건
- `sentiment`: 클래스별 10건
- `routing`: 클래스별 10건

이 축별 평가셋들을 합친 결과가 `analysis_eval_all_axes_10_each_20260616.csv`다.

### 2. 수동 라벨 검토

`analysis_eval_label_sample_20260616.csv`에는 `notes` 컬럼이 있고, 각 샘플에 대해 왜 해당 gold label을 부여했는지 짧은 판단 근거가 적혀 있다. 따라서 이 평가셋은 자동 수집본이 아니라, 사람이 케이스를 보고 라벨 타당성을 확인한 수동 검토 기반 데이터라고 보는 것이 맞다.

### 3. 수동 재라벨 적용

`manual_relabel_analysis_eval_sets.py`는 합본 CSV를 다시 열어 `ticket_id`별 override를 적용한다.

- override 등록 건수: `78`
- 적용 내용:
  - `gold_category`
  - `gold_risk_level`
  - `gold_sentiment`
  - `gold_routing_target`
- 적용 후:
  - 모든 행의 `review_status`를 `manual_checked`로 변경
  - 축별 파생 CSV도 다시 생성

즉, 현재 평가셋은 다음 성격을 가진다.

1. 축별 대표 사례를 뽑아 만든 의도적 샘플셋
2. 사람이 gold label을 직접 점검한 수동 검토셋
3. 일부 샘플은 후속 재라벨링으로 정답이 수정된 정제셋

## 4. 평가 산출물

`apps/tests/cs-auto_tests/eval` 아래에는 동일 데이터셋에 대한 실행 결과가 2회 저장되어 있다.

- `20260616_155524/analysis_agent`
- `20260616_170839/analysis_agent`

각 실행은 아래 산출물을 남긴다.

- `report.json`
- `accuracy_summary.csv`
- `mismatches.csv`
- `confusion_matrix.md`

문서 해석은 최신 결과인 `20260616_170839/analysis_agent/report.json`을 기준으로 한다.

## 5. 최신 성능 요약

최신 실행(`20260616_170839`) 기준 정확도는 아래와 같다.

| axis | correct | total | accuracy |
| --- | ---: | ---: | ---: |
| category | 126 | 143 | 0.8811 |
| risk_level | 132 | 143 | 0.9231 |
| sentiment | 111 | 143 | 0.7762 |
| routing_target | 117 | 143 | 0.8182 |

전체적으로 보면:

- `risk_level`이 가장 안정적이다.
- `category`도 실무 사용에 가까운 수준으로 나온다.
- `sentiment`는 상대적으로 약하다.
- `routing_target`은 category/risk보다 낮지만 최신 실행에서는 실사용 가능한 수준까지 올라와 있다.

## 6. 성능 해석

### 6-1. category 해석

`category` 정확도는 `88.11%`다.

주요 오분류는 다음과 같다.

- `payment -> refund`: 4건
- `payment -> bug`: 3건
- `general -> bug`: 3건
- `account -> policy`: 2건

해석:

- `payment`와 `refund`는 결제 실패, 중복 결제, 환불 요청이 한 문장 안에 같이 등장하는 경우가 많아 경계가 겹친다.
- `payment`와 `bug`도 “결제 오류”처럼 기능 장애와 결제 이슈가 동시에 나타나는 케이스에서 흔들린다.
- `general -> bug`는 단순 문의와 실제 장애 제보의 구분이 애매한 문장형 케이스에서 발생한 것으로 볼 수 있다.

즉, 카테고리 분류의 약점은 전반적 실패라기보다 경계 사례에서의 클래스 충돌에 가깝다.

### 6-2. risk_level 해석

`risk_level` 정확도는 `92.31%`다.

주요 오분류는 다음과 같다.

- `LOW -> HIGH`: 3건
- `HIGH -> MID`: 3건
- `HIGH -> LOW`: 3건
- `MID -> LOW`: 2건

해석:

- 위험도는 전반적으로 잘 맞지만, `HIGH` 판정 기준이 문맥상 강한 불만, 계정 문제, 결제 피해, 제재 이슈와 얼마나 결합됐는지에 따라 흔들린다.
- 특히 단순 불만 표현과 실제 고위험 운영 이슈를 분리하는 기준이 프롬프트나 규칙에서 더 명확해질 여지가 있다.

### 6-3. sentiment 해석

`sentiment` 정확도는 `77.62%`로 4개 축 중 가장 낮다.

주요 오분류는 다음과 같다.

- `neutral -> positive`: 11건
- `negative -> neutral`: 11건
- `neutral -> negative`: 9건

또한 mismatch 집계에서도 `sentiment` 오류가 `32`건으로 가장 많다.

해석:

- 이 축은 극단 감정보다 “중립이지만 불만이 섞인 문의”, “감사 표현이 있으나 본질은 클레임인 문의” 같은 혼합 톤에서 가장 흔들린다.
- CS 문장은 정보 요청과 불만 표현이 동시에 들어가는 경우가 많아서, 일반 감성분석보다 더 어렵다.
- 따라서 sentiment는 현재 단계에서는 보조 신호로는 유효하지만, 독립적인 의사결정 축으로는 신뢰도를 보수적으로 잡는 편이 맞다.

### 6-4. routing_target 해석

`routing_target` 정확도는 `81.82%`다.

주요 오분류는 다음과 같다.

- `DB_only -> doc_only`: 6건
- `DB_only -> DB&DOC`: 6건
- `doc_only -> DB&DOC`: 5건
- `DB&DOC -> doc_only`: 3건

해석:

- 라우팅 오류의 핵심은 “DB 확인이 꼭 필요한가”, “문서 안내만으로 충분한가”의 경계 판단이다.
- 즉, retrieval 경로 선택 문제이지, 완전히 엉뚱한 라우팅보다는 인접 경로 간 혼동이 많다.
- `fixed_answer` 오분류는 상대적으로 적어서, 완전 정형 답변 여부 판단은 비교적 안정적인 편이다.

## 7. 두 번 실행된 결과의 해석

같은 데이터셋으로 저장된 두 실행 결과를 비교하면:

| run | category | risk | sentiment | routing |
| --- | ---: | ---: | ---: | ---: |
| `20260616_155524` | 0.8811 | 0.9231 | 0.7762 | 0.5664 |
| `20260616_170839` | 0.8811 | 0.9231 | 0.7762 | 0.8182 |

관찰 포인트:

- `category`, `risk_level`, `sentiment`는 두 실행이 완전히 같다.
- `routing_target`만 `0.5664 -> 0.8182`로 크게 달라졌다.

해석:

- 현재 파이프라인에서 라우팅 단계가 다른 축보다 더 민감하거나 비결정적일 가능성이 높다.
- 저장소 기준으로 확인 가능한 사실은 “같은 평가셋에서 라우팅 결과 변동폭이 크다”는 점이다.
- 따라서 성능 보고 시에는 최신 수치만 쓰기보다, 라우팅은 재실행 안정성까지 같이 점검하는 것이 맞다.

원인 자체는 이 문서만으로 단정할 수 없지만, 일반적으로는 다음 가능성을 우선 의심할 수 있다.

- 라우팅만 LLM 의존도가 더 높음
- 프롬프트 또는 후처리 규칙이 직전 실행과 달라졌음
- 모델 응답의 비결정성이 큼

## 8. 실무 관점 결론

현재 평가 결과를 실무적으로 해석하면 다음과 같다.

- `category`, `risk_level`은 운영 보조 분류기로 충분히 활용 가능하다.
- `sentiment`는 우선순위 보조 신호 정도로 사용하는 것이 안전하다.
- `routing_target`은 최신 결과는 양호하지만, 재실행 안정성을 별도로 계속 봐야 한다.
- 데이터셋이 전부 `naver_cafe` 소스이므로, 다른 채널로 일반화된다고 바로 가정하면 안 된다.

## 9. 재실행 방법

테스트 함수는 live eval을 기본 skip 하므로 아래 조건이 필요하다.

- 환경 변수 `CS_AUTO_RUN_LIVE_EVAL=1`
- `.env` 또는 환경 변수에 `LLM_API_KEY`, `LLM_MODEL` 설정

실행 예:

```powershell
$env:CS_AUTO_RUN_LIVE_EVAL="1"
python -m pytest apps/tests/cs-auto_tests/eval/test_analysis_agent_eval.py -s
```

직접 실행 모드 예:

```powershell
python apps/tests/cs-auto_tests/eval/test_analysis_agent_eval.py
```

실행 후 결과는 `apps/tests/cs-auto_tests/eval/<timestamp>/analysis_agent` 아래에 저장된다.
