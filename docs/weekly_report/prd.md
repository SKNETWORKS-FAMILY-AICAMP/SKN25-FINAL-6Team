# Weekly Report PRD

## 목적

현재 `apps/weekly_report`의 목표는 최근 7일 운영 데이터를 요약한 주간 리포트를 생성하고, 이를 PDF와 Slack 메시지로 전달하는 것이다.

이 문서는 **현재 구현 범위**를 기준으로 작성한다. 과거의 대시보드/Streamlit 요구사항은 이 문서의 범위에서 제외한다.

## 사용자

| 사용자 | 목적 |
| --- | --- |
| 게임기획팀 | 주간 문의 흐름, 리스크, 개선 요청 Top 5, AI 권장 액션 파악 |
| 운영 담당자 | 수동 실행, PDF 확인, Slack 전송 상태 확인 |
| 운영/배치 담당자 | Airflow 정기 실행, 장애 시 재실행 |

## 현재 제공 기능

### 실행

| ID | 요구사항 |
| --- | --- |
| `FR-WR-001` | 시스템은 `report.run(days=7)`로 주간 리포트를 생성할 수 있어야 한다. |
| `FR-WR-002` | 시스템은 `GET /health`로 DB 연결 상태를 확인할 수 있어야 한다. |
| `FR-WR-003` | 시스템은 `POST /report/trigger`로 수동 실행을 할 수 있어야 한다. |
| `FR-WR-004` | 시스템은 Airflow DAG `dashboard_weekly_report`로 매주 월요일 09:00 KST 자동 실행할 수 있어야 한다. |

### 데이터 수집

| ID | 요구사항 |
| --- | --- |
| `FR-WR-101` | 시스템은 `qa_ticket`를 기준으로 기간 내 티켓 수, 초안 수, 응답 수, safety 수를 집계해야 한다. |
| `FR-WR-102` | 시스템은 `ticket_analysis`에서 카테고리, 응답 유형, 리스크, 감성, 라우팅 정보를 읽어야 한다. |
| `FR-WR-103` | 시스템은 `insight`가 있을 경우 티켓당 최신 1건을 조인해야 한다. |
| `FR-WR-104` | 시스템은 `community_users.nickname`을 표시용으로 읽을 수 있어야 한다. |
| `FR-WR-105` | 시스템은 `voc_feedback.topic_keywords`가 존재하면 Top 5 개선 요청 키워드에 활용할 수 있어야 한다. |

### 리포트 구성

| ID | 요구사항 |
| --- | --- |
| `FR-WR-201` | 리포트는 요약 수치, 전주 비교, 분포, Top 5 개선 요청, 이상 감지, AI 권장 액션을 포함해야 한다. |
| `FR-WR-202` | 리포트는 고위험, 부정 감성, `human_review`, `urgent_alert` 성격의 행을 검토 대상으로 표시해야 한다. |
| `FR-WR-203` | 리포트는 선택된 검토 행에 대해 AI 해석 문장을 포함할 수 있어야 한다. |
| `FR-WR-204` | 리포트는 PDF로 렌더링 가능해야 한다. |
| `FR-WR-205` | 리포트는 Slack 채널 ID가 주어지면 PDF를 업로드할 수 있어야 한다. |

### AI 기능

| ID | 요구사항 |
| --- | --- |
| `FR-WR-301` | 시스템은 요약/이상 감지/Top 5 결과를 바탕으로 3~5개의 AI 권장 액션을 생성할 수 있어야 한다. |
| `FR-WR-302` | 시스템은 LLM 설정이 없거나 실패하면 fallback 권장 액션을 반환해야 한다. |
| `FR-WR-303` | 시스템은 검토용 행 목록에 대해 행별 AI 해석을 생성할 수 있어야 한다. |
| `FR-WR-304` | 시스템은 행별 AI 해석 생성 실패 시 deterministic fallback 문장을 사용해야 한다. |

## 비기능 요구사항

| ID | 요구사항 |
| --- | --- |
| `NFR-WR-001` | 리포트는 읽기 전용 DB 조회만 사용해야 한다. |
| `NFR-WR-002` | Slack 채널 미지정 상태에서 `send_to_slack=True`이면 명시적 오류를 반환해야 한다. |
| `NFR-WR-003` | Slack 토큰 또는 채널 오류는 `SlackReportError`로 구분되어야 한다. |
| `NFR-WR-004` | `voc_feedback` 조회 실패는 전체 리포트 실패로 이어지지 않아야 한다. |
| `NFR-WR-005` | 현재 구현은 `/summary/*`, `/tickets*` 같은 대시보드 API를 제공하지 않는다는 점이 문서와 일치해야 한다. |

## 범위 제외

- Streamlit 또는 웹 대시보드 UI
- `/summary/overview`, `/summary/risk`, `/summary/quality`, `/tickets`, `/tickets/{ticket_id}` API
- 운영자가 웹 화면에서 직접 결제/환불/지급을 수행하는 기능
- `insight` 테이블 생성 또는 적재 책임
- 실시간 알림 시스템

## 현재 구조에서 주의할 점

- `top_requests.py`는 `voc_feedback`를 읽으려 하지만, 라이브 DB 문서에는 이 테이블이 없다.
- 구현은 예외를 흡수하고 `topic_keywords=[]`로 진행하므로 리포트 전체는 계속 생성된다.
- 따라서 이 문서는 `voc_feedback`을 **선택적 보조 데이터**로 취급한다.
