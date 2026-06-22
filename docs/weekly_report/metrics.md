# Weekly Report Metrics

## 목적

이 문서는 `apps/weekly_report`가 **현재 실제로 계산하는 값만** 정리한다.

구현 기준 파일:

- `apps/weekly_report/db/metrics.py`
- `apps/weekly_report/db/analysis.py`
- `apps/weekly_report/db/top_requests.py`
- `apps/weekly_report/db/spike_alerts.py`
- `apps/weekly_report/build/payload.py`

## 기간 기준

- 기본 기간: 최근 7일
- 현재 기간: `window_start <= x < window_end`
- 비교 기간: 직전 동일 길이 구간
- `metrics.py`와 `spike_alerts.py`는 주로 `qa_ticket.inquiry_created_at` 기준
- `analysis.py`는 `ticket_analysis.analyzed_at` 기준

## `db.metrics.fetch()`가 계산하는 값

### 커버리지 / 처리 지표

| 키 | 의미 | 사용 테이블 |
| --- | --- | --- |
| `total_tickets` | 기간 내 전체 티켓 수 | `qa_ticket` |
| `responded_tickets` | 응답이 있는 티켓 수 | `qa_ticket`, `final_response` |
| `draft_tickets` | 초안이 1개 이상 있는 티켓 수 | `qa_ticket`, `answer_draft` |
| `analyzed_tickets` | 분석 행이 1개 이상 있는 티켓 수 | `qa_ticket`, `ticket_analysis` |
| `response_rate` | `responded_tickets / total_tickets` | same |
| `analysis_coverage_rate` | `analyzed_tickets / total_tickets` | same |
| `draft_coverage_rate` | `draft_tickets / total_tickets` | same |
| `draft_ticket_rate` | 초안 보유 티켓 비율 | `qa_ticket`, `answer_draft` |
| `final_response_ticket_rate` | 최종 응답 보유 티켓 비율 | `qa_ticket`, `final_response` |
| `draft_count` | 초안 전체 건수 | `answer_draft` |
| `safety_check_count` | safety check 전체 건수 | `safety_results`, `answer_draft`, `qa_ticket` |

### 카테고리 집계

| 키 | 의미 | 사용 테이블 |
| --- | --- | --- |
| `category_counts` | 티켓별 최신 `ticket_analysis.category` 분포 | `qa_ticket`, `ticket_analysis` |

## `db.analysis.fetch_analysis_rows()`가 가져오는 행

행 단위 주요 컬럼:

- `analysis_id`
- `ticket_id`
- `category`
- `responder_type`
- `enriched_query`
- `risk_level`
- `sentiment`
- `routing_target`
- `summary`
- `analyzed_at`
- `title`
- `status`
- `source_type`
- `inquiry_created_at`
- `nickname`
- `insight_id`
- `content_summary`
- `insight_category`
- `insight_sentiment`
- `insight_risk_level`
- `pattern_risk_level`
- `insight_created_at`

`insight`는 티켓당 최신 1건만 `LEFT JOIN LATERAL`로 붙인다.

## `build_report_payload()`가 추가로 계산하는 값

### 요약 수치

| 키 | 의미 |
| --- | --- |
| `analysis_count` | 현재 기간 분석 행 수 |
| `distinct_ticket_count` | 중복 제거된 티켓 수 |
| `repeat_analysis_count` | 같은 티켓에 여러 분석 행이 있는 수량 |
| `high_risk_count` | `risk_level in {high, critical}` |
| `negative_sentiment_count` | `sentiment in {negative, very_negative}` |
| `human_review_count` | `routing_target == human_review` |
| `urgent_alert_count` | `routing_target == urgent_alert` |
| `blank_query_count` | `enriched_query` 비어 있는 행 수 |
| `blank_summary_count` | `summary` 비어 있는 행 수 |
| `analysis_freshness_hours` | `generated_at - analyzed_at` 평균 시간 |
| `insight_high_rate` | `insight_risk_level` 또는 `pattern_risk_level`이 high/critical인 비율 |

### 전주 비교

`comparisons`에는 아래 4개 비교가 들어간다.

- `analysis_count`
- `high_risk_count`
- `negative_sentiment_count`
- `human_review_count`

각 항목은 `current`, `previous`, `change` 또는 `change_rate`를 포함한다.

### 분포

아래 분포가 payload에 포함된다.

- `category_distribution`
- `responder_distribution`
- `risk_distribution`
- `sentiment_distribution`
- `routing_distribution`

## `top_requests.fetch()` 결과

Top 5 개선 요청은 아래 규칙으로 계산한다.

- 기준 테이블: `ticket_analysis` + `qa_ticket`
- 보조 키워드: `voc_feedback.topic_keywords`가 있으면 사용
- 점수식: `(count * 0.4) + (severity_score * 0.6)`
- `severity_score`: `critical=4`, `high=3`, `medium=2`, `low=1`, `unknown=1`
- 출력 수: 최대 5개

반환 항목 예:

- `rank`
- `category`
- `count`
- `severity_score`
- `priority_score`
- `level`
- `improvement_type`
- `topic_keywords`

## `spike_alerts.detect()` 결과

### `hourly`

- 기준: `qa_ticket.inquiry_created_at`
- 현재 주간의 시간대별 건수와 과거 4주 동일 시간대 평균/표준편차 비교
- 임계치:
  - `zscore >= 2.0` -> `warning`
  - `zscore >= 3.0` -> `critical`

### `daily`

- 현재 주간과 직전 주간의 요일별 건수 비교
- 임계치:
  - `pct_change >= 0.5` -> `warning`
  - `pct_change >= 1.0` -> `critical`

### `monthly`

- 현재 주간 포함 최근 4개 주간의 총 티켓 수
- 추세 시각화 목적이며 별도 임계치 없음

## 현재 구현에 없는 항목

과거 문서에 있었지만 현재 `apps/weekly_report` 구현에 없는 항목:

- 평균 응답 지연 KPI
- evidence 첨부율 / relevance 평균
- notification 상태 분포
- `/summary/*` 대시보드 응답 스키마
- `/tickets`, `/tickets/{ticket_id}` 상세 화면용 지표
- `insight.risk_level` / `pattern_risk_level` 분포 차트 전용 쿼리

현재 구현은 **주간 리포트 생성에 필요한 최소 집계와 행 데이터**만 사용한다.
