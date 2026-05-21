# Dashboard Screen Design

## 1. 문서 목적

이 문서는 `src/dashboard/frontend` Streamlit 대시보드의 화면 설계 기준을 정의한다. 기준 데이터와 지표는 다음 문서를 따른다.

- `docs/dashboard/architecture.md`: Dashboard API, LangGraph workflow, Streamlit frontend 구조
- `docs/dashboard/api_spec.md`: `/summary/*`, `/tickets`, `/tickets/{ticket_id}` 응답 필드
- `docs/dashboard/metrics.md`: 운영 현황, 리스크 분석, 응답 품질 지표 산식
- `docs/DB/descriptions.md`: `qa_ticket`, `ticket_analysis`, `answer_draft`, `evidence_docs`, `safety_results`, `final_response`, `notification_logs`, `insight`, `voc_feedback` 관계
- `docs/operation/*`: 운영자 검수 흐름과 티켓 처리 맥락

대시보드는 운영자가 매일 확인하는 업무 화면이므로 마케팅형 랜딩 화면이 아니라, 지표 탐색과 이상 징후 파악에 집중한 밀도 있는 업무 도구로 설계한다.

## 2. 사용자와 핵심 과업

| 사용자 | 주요 과업 | 화면 요구 |
| --- | --- | --- |
| 운영 관리자 | 문의 유입, 대기/종료, 처리율 확인 | 첫 화면에서 KPI와 추세를 빠르게 확인 |
| 리스크 담당자 | 고위험 문의, 부정 감성, 안전성 점수 확인 | 위험 지표를 강조하고 상세 후보 목록 제공 |
| 품질 관리자 | 초안, 근거, 안전성, 최종 응답 커버리지 확인 | 응답 품질 병목과 검수 후보를 한 화면에서 비교 |

## 3. 정보 구조

```text
운영 대시보드
├─ 홈: 운영 요약
├─ 운영 현황: ticket_counts, response_metrics, source/status/routing, recent_tickets
├─ 리스크 분석: risk distributions, safety_score_summary, high_risk_tickets
└─ 응답 품질: draft/evidence/safety/final/notification, quality_candidates
```

Streamlit 기본 multipage 구조를 유지한다.

- `src/dashboard/frontend/app.py`: 전체 요약 홈
- `src/dashboard/frontend/pages/1_운영_현황.py`: 운영 현황
- `src/dashboard/frontend/pages/2_리스크_분석.py`: 리스크 분석
- `src/dashboard/frontend/pages/3_응답_품질.py`: 응답 품질

## 4. 공통 화면 레이아웃

### 4.1 기본 그리드

```text
┌──────────────────────────────────────────────────────────────┐
│ Sidebar                                                      │
│ - API URL                                                    │
│ - 조회 기간                                                  │
│ - 페이지별 옵션                                              │
├──────────────────────────────────────────────────────────────┤
│ Page Header                                                  │
│ - 제목                                                       │
│ - 보조 설명 또는 현재 조회 조건                              │
├──────────────────────────────────────────────────────────────┤
│ KPI Row: 4 columns                                           │
├──────────────────────────────────────────────────────────────┤
│ KPI Row 또는 Alert Row: 4 columns                            │
├──────────────────────────────┬───────────────────────────────┤
│ Chart Section Left           │ Chart Section Right            │
│ - chart card                 │ - chart card                    │
│ - chart card                 │ - chart card                    │
├──────────────────────────────┴───────────────────────────────┤
│ Data Table                                                    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 공통 사이드바

| 항목 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| API URL | `st.text_input` | `http://127.0.0.1:8000` | `DASHBOARD_API_BASE_URL` 또는 세션 상태 사용 |
| 조회 기간 | `st.slider` | 30일 | API `days` 파라미터로 전달 |
| 목록 개수 | `st.slider` | 페이지별 15~20개 | 최근 문의 또는 후보 목록 표시 개수 |

API URL은 `src/dashboard/frontend/state/session_state.py`의 `api_base_url()`로 정규화한다. 빈 값, 스킴 없는 값, 상대 경로 입력은 기본 API URL 또는 `http://` 스킴이 붙은 값으로 보정한다.

## 5. 화면별 설계

### 5.1 홈: 운영 요약

| 구역 | 데이터 | 표시 방식 |
| --- | --- | --- |
| KPI 1행 | `ticket_counts.total`, `pending`, `closed`, `today` | `st.metric` 4열 |
| KPI 2행 | `response_metrics.response_rate`, `draft_coverage_rate`, `analysis_coverage_rate`, `avg_response_latency_minutes` | 퍼센트/분 단위 포맷 |
| 차트 좌측 | `source_distribution`, `status_distribution` | bar chart |
| 차트 우측 | `routing_distribution`, `recent_tickets` | bar chart, line chart |
| 테이블 | `recent_tickets` | 최근 문의 목록 |

홈은 전체 운영 상태를 가장 빠르게 파악하는 화면이다. KPI 값은 과도한 장식보다 숫자 가독성을 우선한다. 평균 응답 지연은 값이 없으면 `-`로 표시한다.

### 5.2 운영 현황

| 구역 | 데이터 | 표시 방식 |
| --- | --- | --- |
| KPI 1행 | 전체, 대기, 종료, 오늘 접수 | 4열 metric |
| KPI 2행 | 응답률, 초안률, 분석률, 평균 응답 지연 | 4열 metric |
| 차트 | 접수 채널, 상태 분포, 라우팅 대상 | bar chart |
| 보조 카드 | 조회 기간 | compact metric card |
| 테이블 | `recent_tickets` | `ticket_id`, `title`, `status`, `source_type`, `nickname`, `category`, `risk_level`, `routing_target`, `inquiry_created_at` |

운영 현황은 티켓 처리량과 병목 탐지에 집중한다. 상태 컬럼은 색상 배지를 적용할 수 있도록 `pending`, `closed` 등 원본 값을 유지한다.

### 5.3 리스크 분석

| 구역 | 데이터 | 표시 방식 |
| --- | --- | --- |
| Safety KPI | 평균 환각, 평균 유해성, 평균 정책 위반, 평균 사실성 | 4열 metric |
| 리스크 차트 | `analysis_risk_distribution`, `insight_risk_distribution`, `pattern_risk_distribution` | bar chart |
| 감성 차트 | `sentiment_distribution` | bar chart |
| 테이블 | `high_risk_tickets` | 고위험 문의 후보 |

리스크 화면은 위험도가 높은 데이터를 먼저 눈에 띄게 해야 한다. `critical`, `high` 값은 테이블에서 강조 색상을 적용하고, 안전성 평균 점수는 threshold 기준을 보조 설명으로 둔다.

기본 threshold:

| 항목 | 경고 조건 |
| --- | --- |
| 환각 | `avg_hallucination_score >= 0.7` |
| 유해성 | `avg_toxicity_score >= 0.7` |
| 정책 위반 | `avg_policy_violation_score >= 0.7` |
| 사실성 | `avg_factuality_score <= 0.3` |

### 5.4 응답 품질

| 구역 | 데이터 | 표시 방식 |
| --- | --- | --- |
| KPI 1행 | `draft_count`, `evidence_linked_drafts`, `final_response_count`, `safety_check_count` | 4열 metric |
| KPI 2행 | `draft_ticket_rate`, `evidence_attachment_rate`, `final_response_ticket_rate`, `avg_final_latency_minutes` | 4열 metric |
| 차트 좌측 | `notification_summary`, evidence count | bar chart |
| 차트 우측 | 평균 환각/유해성/정책위반/사실성 | bar chart |
| 테이블 | `quality_candidates` | 검수 우선 후보 |

응답 품질 화면은 초안 생성부터 최종 응답까지의 커버리지를 보여준다. 품질 후보 테이블은 낮은 `factuality_score`와 높은 `hallucination_score`를 우선 검수하도록 정렬된 API 응답을 그대로 사용한다.

## 6. 컴포넌트 설계

### 6.1 Metric Card

현재 구현은 `st.metric` 또는 `render_metric_card()`를 사용한다. CSS 적용 후에는 Streamlit metric DOM을 카드형 KPI로 보이게 한다.

상태:

| 상태 | 표시 |
| --- | --- |
| 정상 값 | 큰 숫자, 작은 라벨 |
| 값 없음 | `-` |
| 위험 값 | `.metric-risk` wrapper 또는 `st.warning` 보조 표시 |

### 6.2 Chart Box

`render_chart_box(title, data, kind="bar")`를 기준으로 한다.

| 상태 | 표시 |
| --- | --- |
| 데이터 있음 | `st.bar_chart` 또는 `st.line_chart` |
| 데이터 없음 | 카드 내부 `st.info("표시할 데이터가 없습니다.")` |
| 필드 불일치 | `st.write(data)` fallback |

### 6.3 Data Table

`render_data_table(rows)`는 `st.dataframe(..., use_container_width=True, hide_index=True)`를 사용한다.

권장 컬럼 처리:

- 날짜: `YYYY-MM-DD HH:mm`
- 비율: `0.0%`
- 점수: 소수점 둘째 자리
- 긴 제목: 말줄임 대신 테이블 가로 스크롤 허용
- 위험도: `critical`, `high`, `medium`, `low` 원본 값 유지

## 7. Streamlit CSS 설계

Streamlit은 DOM 클래스명이 버전에 따라 바뀔 수 있으므로, 가능한 한 `data-testid`와 안정적인 구조 선택자를 사용한다. CSS는 각 페이지 상단 또는 공통 헬퍼에서 `st.markdown(..., unsafe_allow_html=True)`로 주입한다.

### 7.1 적용 방식

권장 공통 함수:

```python
import streamlit as st


def inject_dashboard_css() -> None:
    st.markdown(
        """
        <style>
        /* CSS content */
        </style>
        """,
        unsafe_allow_html=True,
    )
```

페이지 시작 순서:

```python
st.set_page_config(page_title="운영 대시보드", layout="wide")
init_session_state()
inject_dashboard_css()
```

### 7.2 권장 CSS

```css
:root {
  --dash-bg: #f6f7f9;
  --dash-surface: #ffffff;
  --dash-surface-muted: #f1f3f5;
  --dash-border: #d7dde5;
  --dash-text: #18202b;
  --dash-muted: #667085;
  --dash-accent: #1769aa;
  --dash-accent-soft: #e8f2fb;
  --dash-danger: #b42318;
  --dash-danger-soft: #fff1f0;
  --dash-warning: #b54708;
  --dash-warning-soft: #fff7e6;
  --dash-success: #067647;
  --dash-success-soft: #eaf8ef;
}

.stApp {
  background: var(--dash-bg);
  color: var(--dash-text);
}

section[data-testid="stSidebar"] {
  background: #111827;
  border-right: 1px solid #1f2937;
}

section[data-testid="stSidebar"] * {
  color: #f9fafb;
}

section[data-testid="stSidebar"] input {
  background: #ffffff;
  color: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
}

section[data-testid="stSidebar"] [data-testid="stSlider"] {
  padding-top: 4px;
}

.main .block-container {
  max-width: 1440px;
  padding-top: 24px;
  padding-bottom: 48px;
}

h1 {
  color: var(--dash-text);
  font-size: 28px;
  line-height: 1.25;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 4px;
}

h2,
h3 {
  color: var(--dash-text);
  letter-spacing: 0;
}

[data-testid="stCaptionContainer"] {
  color: var(--dash-muted);
}

div[data-testid="stMetric"] {
  background: var(--dash-surface);
  border: 1px solid var(--dash-border);
  border-radius: 8px;
  padding: 16px 18px;
  min-height: 112px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
}

div[data-testid="stMetric"] label {
  color: var(--dash-muted);
  font-size: 13px;
  line-height: 1.3;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: var(--dash-text);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--dash-surface);
  border: 1px solid var(--dash-border);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

div[data-testid="stVerticalBlockBorderWrapper"] p strong {
  display: inline-block;
  color: var(--dash-text);
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}

[data-testid="stDataFrame"] {
  background: var(--dash-surface);
  border: 1px solid var(--dash-border);
  border-radius: 8px;
  overflow: hidden;
}

[data-testid="stAlert"] {
  border-radius: 8px;
  border: 1px solid var(--dash-border);
}

button[kind="primary"],
button[kind="secondary"] {
  border-radius: 6px;
  font-weight: 600;
}

button[kind="primary"] {
  background: var(--dash-accent);
  border-color: var(--dash-accent);
}

button[kind="secondary"] {
  background: var(--dash-surface);
  border-color: var(--dash-border);
  color: var(--dash-text);
}

@media (max-width: 900px) {
  .main .block-container {
    padding-left: 16px;
    padding-right: 16px;
  }

  div[data-testid="stMetric"] {
    min-height: 96px;
    padding: 14px;
  }

  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 24px;
  }
}
```

### 7.3 위험도 배지 확장 CSS

`st.dataframe` 내부 셀별 스타일링은 제한적이므로, 위험도 후보를 별도 HTML 카드나 `st.data_editor` 스타일러로 확장할 때 다음 색상 토큰을 사용한다.

```css
.risk-badge {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.risk-critical {
  color: var(--dash-danger);
  background: var(--dash-danger-soft);
  border: 1px solid #fecdca;
}

.risk-high {
  color: var(--dash-warning);
  background: var(--dash-warning-soft);
  border: 1px solid #fedf89;
}

.risk-medium {
  color: var(--dash-accent);
  background: var(--dash-accent-soft);
  border: 1px solid #b9dcf5;
}

.risk-low {
  color: var(--dash-success);
  background: var(--dash-success-soft);
  border: 1px solid #abefc6;
}
```

## 8. 시각 스타일 가이드

| 항목 | 기준 |
| --- | --- |
| 톤 | 업무용, 차분함, 고대비 |
| 배경 | 밝은 회색 앱 배경 + 흰색 데이터 카드 |
| 라운드 | 8px 이하 |
| 강조색 | 파란색은 액션/선택, 빨간색은 위험, 초록색은 정상 |
| 타이포그래피 | Streamlit 기본 폰트 사용, 제목 28px 수준, 카드 내부 과대 제목 금지 |
| 차트 | 기본 `st.bar_chart`, `st.line_chart` 유지. 색상 커스터마이징이 필요하면 Altair 전환 |
| 여백 | KPI 간격은 좁게, 섹션 간격은 명확하게 |

## 9. 반응형 기준

| 너비 | 동작 |
| --- | --- |
| 1200px 이상 | 4열 KPI, 2열 차트 |
| 900~1199px | 4열 KPI 유지, 차트 2열 가능 |
| 900px 미만 | Streamlit 컬럼이 자연스럽게 수직 배치되도록 허용 |

텍스트가 버튼이나 카드 내부에서 잘리지 않도록, 긴 라벨은 축약하지 말고 카드 폭을 확보한다. 모바일에서는 사이드바에 필터가 접히므로 페이지 본문 상단에 현재 조회 기간을 캡션으로 표시하는 것을 권장한다.

## 10. 상태 설계

| 상태 | 처리 |
| --- | --- |
| API 실패 | `st.error("... 불러오지 못했습니다: {exc}")` 후 `st.stop()` |
| 데이터 없음 | 차트/테이블 영역 내부에 `st.info("표시할 데이터가 없습니다.")` |
| 평균값 없음 | `-` |
| URL 입력 오류 | `api_base_url()`에서 보정. 보정 불가 시 기본 URL 사용 |
| 느린 응답 | 추후 `st.spinner("데이터를 불러오는 중입니다.")` 적용 권장 |

## 11. 접근성 기준

- 색상만으로 위험도를 전달하지 않고 `critical`, `high` 등 텍스트 값을 함께 표시한다.
- metric 라벨은 13px 이상, metric 값은 24px 이상을 유지한다.
- 차트 제목은 카드 상단 텍스트로 제공한다.
- 테이블은 원본 컬럼명을 유지하되, 필요 시 한국어 표시명 매핑을 별도 함수에서 적용한다.
- `st.info`, `st.error`, `st.warning`을 상태 메시지에 사용해 스크린리더가 의미를 파악할 수 있게 한다.

## 12. 구현 체크리스트

- [ ] 공통 CSS 주입 함수 추가: 예 `src/dashboard/frontend/components/style.py`
- [ ] 모든 dashboard 페이지에서 `inject_dashboard_css()` 호출
- [ ] 깨진 한글 라벨 정리
- [ ] KPI 숫자 포맷 통일: 개수, 비율, 분, 점수
- [ ] 차트/테이블 빈 상태 문구 통일
- [ ] 리스크 테이블 위험도 강조 확장 검토
- [ ] API URL 정규화 동작 유지
- [ ] `pytest tests/dashboard` 또는 최소 frontend helper 단위 테스트 실행

## 13. 화면별 완료 기준

| 화면 | 완료 기준 |
| --- | --- |
| 홈 | `/summary/overview` 호출 성공, KPI 8개, 차트 4개, 최근 문의 테이블 표시 |
| 운영 현황 | 조회 기간 변경 시 지표와 테이블 갱신 |
| 리스크 분석 | safety score가 없을 때 `-`, 고위험 테이블이 비어 있으면 빈 상태 표시 |
| 응답 품질 | `/summary/quality` 호출 성공, coverage metric과 quality candidates 표시 |
| 공통 | API URL이 비어 있어도 `Invalid URL '/summary/...'`가 발생하지 않음 |

