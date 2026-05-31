# Frontend-Backend Connection Map

이 문서는 `chatbot`, `cs_auto`, `dashboard` 세 시스템에서:

- 프론트가 실제로 호출하는 API
- 해당 API가 연결하는 백엔드 로직
- 프론트에 이미 노출되는 데이터
- 백엔드에는 있지만 아직 프론트에 직접 연결되지 않은 기능

을 한 번에 정리한 문서다.

기준 소스:

- `apps/chatbot/frontend/static/index.html`
- `apps/chatbot/backend/api/main.py`
- `apps/cs_auto/frontend/static/index.html`
- `apps/cs_auto/backend/api/main.py`
- `apps/dashboard/frontend/static/index.html`
- `apps/dashboard/backend/api/main.py`

## 1. Chatbot

### 1.1 현재 프론트에서 실제 호출하는 API

| 프론트 호출 | 백엔드 엔드포인트 | 연결되는 백엔드 로직 | 프론트에서 쓰는 목적 |
| --- | --- | --- | --- |
| `GET /server-regions` | `server_regions()` | `chatbot.service.account_service.get_server_regions()` | 로그인 화면의 서버 선택 목록 |
| `POST /login` | `login()` | `chatbot.service.account_service.login_with_credentials()` | 계정 인증 후 `user_id`, `account_id`, `nickname`, `server_region` 수신 |
| `GET /tickets?user_id=...&account_id=...` | `list_tickets()` | `qa_ticket` + 최신 `final_response` 조회 SQL | 문의 이력 화면 구성 |
| `POST /chat` | `chat()` | `chatbot.service.chatbot_service.run_chatbot()` | 질문 입력 후 AI 응답, 카테고리, 라우팅, 리뷰 필요 여부 수신 |

### 1.2 프론트까지 연결되는 실제 로직

#### A. 로그인

흐름:

1. 프론트가 이메일, 비밀번호, 서버를 입력한다.
2. `POST /login` 호출
3. `login_with_credentials()`가 계정 검증
4. 성공 시 프론트는 `user_id`, `account_id`, `email`, `nickname`, `server_region`를 상태로 저장

프론트 반영:

- 로그인 성공 후 채팅 화면 진입
- 좌측 계정 카드에 연결된 계정 표시
- 이후 문의 이력 조회와 채팅 호출의 기준 키로 사용

#### B. 문의 이력

흐름:

1. 로그인 성공 후 프론트가 `GET /tickets` 호출
2. 백엔드는 `qa_ticket`와 최신 `final_response`를 묶어 반환
3. 프론트는 티켓 제목, 상태, 원문, 최종 응답을 이력 카드에 렌더링

프론트 반영:

- `Inquiry History` 화면
- 과거 문의 목록
- 각 문의의 최종 응답 요약

#### C. 챗봇 응답 생성

흐름:

1. 프론트가 `POST /chat`
2. `run_chatbot()` 실행
3. 백엔드가 답변 문자열과 함께 내부 상태의 일부를 응답으로 반환

현재 프론트가 받는 주요 값:

- `answer`
- `category`
- `routing_target`
- `review_required`
- `safety_passed`

프론트 반영:

- 중앙 채팅 패널의 AI 답변
- FAQ/카테고리 전환 흐름의 보조 상태

### 1.3 백엔드에는 있지만 프론트에서 직접 안 쓰는 부분

`run_chatbot()` 내부에서는 더 많은 상태 전이가 일어날 수 있지만, 현재 프론트는 최종 응답과 일부 라우팅 메타데이터만 사용한다.

즉 현재 프론트에 직접 연결된 범위는:

- 계정 인증 결과
- 서버 목록
- 티켓 이력
- 챗봇 최종 응답 + 최소 메타데이터

아직 프론트에 직접 노출되지 않는 후보:

- 더 상세한 safety 판단 근거
- 검색된 근거 문서 목록
- 세션 단위 중간 추론 로그

### 1.4 연결 상태 요약

- 연결 완료: 로그인, 서버 목록, 티켓 이력, 챗봇 응답
- 미연결: 세부 추론/근거/중간 상태의 시각화

## 2. CS Auto

### 2.1 현재 프론트에서 실제 호출하는 API

| 프론트 호출 | 백엔드 엔드포인트 | 연결되는 백엔드 로직 | 프론트에서 쓰는 목적 |
| --- | --- | --- | --- |
| `GET /tickets/today?...` | `list_today_tickets()` | `_list_ticket_rows(..., today_only=True)` | 오늘 처리 대상 문의 목록 |
| `GET /tickets?...` | `list_tickets()` | `_list_ticket_rows(...)` | 전체/상태별 문의 목록 |
| `GET /tickets/{ticket_id}` | `get_ticket_detail()` | 티켓 + 분석 + draft + evidence + safety + final + notification + review log 묶음 조회 | 상세 패널 렌더링 |
| `POST /tickets/{ticket_id}/run-workflow` | `run_workflow()` | `build_operation_graph().invoke(OperationState(...))` | AI 초안 생성/재생성 |
| `PATCH /drafts/{draft_id}` | `edit_draft()` | `answer_draft` 수정 + review log 기록 | 검수자가 draft 수정 저장 |
| `POST /drafts/{draft_id}/approve` | `approve_draft()` | `final_response` 생성 + `qa_ticket.status=closed` + review log | draft 승인 및 종료 |
| `POST /drafts/{draft_id}/reject` | `reject_draft()` | `qa_ticket.status=pending` + review log + 재실행 URL 반환 | draft 반려 후 재생성 흐름 시작 |

### 2.2 프론트까지 연결되는 실제 로직

#### A. 큐 목록 조회

흐름:

1. 프론트 탭/필터 상태에 따라 `GET /tickets/today` 또는 `GET /tickets`
2. 백엔드는 최신 `draft_id`, 최신 분석의 `risk_level`, `routing_target`까지 함께 반환
3. 프론트는 좌측 티켓 리스트에 우선순위, 카테고리, 상태 배지를 구성

프론트 반영:

- 좌측 queue panel
- 오늘 문의 / 대기 문의 / 종료 문의 / 검수 이력 탭
- 우선순위 필터

#### B. 상세 검수 패널

흐름:

1. 프론트가 선택된 티켓의 `GET /tickets/{ticket_id}` 호출
2. 백엔드는 아래 데이터를 한 번에 묶어 반환

반환 섹션:

- `ticket`
- `analyses`
- `drafts`
- `evidence_docs`
- `safety_results`
- `final_responses`
- `notifications`
- `review_logs`

프론트 반영:

- 원문의 상세 내용
- AI 분석 요약
- 현재 draft 본문
- safety 점수
- evidence 목록
- 검수 이력

#### C. 워크플로 실행

흐름:

1. 프론트에서 `POST /tickets/{ticket_id}/run-workflow`
2. 백엔드가 `build_operation_graph()`로 operation workflow graph 생성
3. `OperationState(ticket_id=...)`로 워크플로 실행
4. 결과로 `draft_id`, `analysis_id`, `response_id`, `status`, `final_answer`를 반환
5. 프론트는 이후 목록/상세를 다시 조회해서 화면을 갱신

프론트 반영:

- draft 생성 버튼
- 반려 후 재생성
- 진행중 workflow overlay

#### D. draft 수정

흐름:

1. 프론트가 `PATCH /drafts/{draft_id}`
2. 백엔드는 `answer_draft.draft_text` 수정
3. `admin_event_logs`에 `edited` review log 기록
4. 프론트가 상세 재조회

프론트 반영:

- draft textarea 편집
- 수정 저장

#### E. draft 승인

흐름:

1. 프론트가 `POST /drafts/{draft_id}/approve`
2. 백엔드는 `final_response` 생성
3. `qa_ticket.status`를 `closed`로 변경
4. `admin_event_logs`에 `approved` 기록
5. 프론트가 목록/상세 재조회

프론트 반영:

- 타임라인 완료 상태
- 검수 완료 문의로 이동
- 최종 응답 데이터 반영

#### F. draft 반려

흐름:

1. 프론트가 `POST /drafts/{draft_id}/reject`
2. 백엔드는 `qa_ticket.status`를 `pending`으로 변경
3. `admin_event_logs`에 `rejected` 기록
4. 응답에 `run_workflow_url` 반환
5. 프론트가 그 URL로 다시 워크플로 실행

프론트 반영:

- 반려 사유 입력
- 자동 재생성 트리거

### 2.3 백엔드에는 있지만 프론트에서 직접 안 쓰는 부분

현재 상세 API는 프론트보다 더 많은 데이터를 담고 있다.

예:

- `notifications`
- `review_logs`의 세부 metadata
- 여러 draft/evidence/safety 결과의 히스토리

현재 프론트는 그중 최신 상태 중심으로만 사용한다.

즉 이미 API에는 있지만 덜 쓰는 데이터:

- 과거 draft 버전 비교
- 다중 safety 검사 히스토리
- notification 실패 사유 상세
- review log metadata의 구조화 표시

### 2.4 연결 상태 요약

- 연결 완료: 큐 조회, 상세 조회, 워크플로 실행, draft 수정, 승인, 반려
- 미세 미연결: 상세 응답 안의 히스토리성 데이터 일부

## 3. Dashboard

### 3.1 현재 프론트에서 실제 호출하는 API

| 프론트 호출 | 백엔드 엔드포인트 | 연결되는 백엔드 로직 | 프론트에서 쓰는 목적 |
| --- | --- | --- | --- |
| `GET /summary/all?days=...` | `summary_all()` | `run_dashboard_workflow("all", days)` | overview/risk/quality 통합 요약 |
| `GET /reports/weekly?days=7` | `weekly_report_preview()` | `run_weekly_report_workflow(days)` | 주간 리포트 내러티브/전달 상태 미리보기 |
| `GET /tickets?days=...&limit=50` | `list_tickets()` | 기간 내 티켓 목록 + 최신 분석/draft/response 메타데이터 조회 | 티켓 리스트/테이블 |
| `GET /tickets/{ticket_id}` | `get_ticket_detail()` | 티켓 + 계정 + 분석 + drafts + evidence + safety + final + notifications + VOC + 결제/환불/아이템/가챠/이벤트 로그 조회 | 우측 상세 패널 |

### 3.2 프론트까지 연결되는 실제 로직

#### A. 통합 대시보드 요약

흐름:

1. 프론트가 `GET /summary/all?days=...`
2. 백엔드가 `run_dashboard_workflow("all", days)` 수행
3. 내부적으로 overview/risk/quality 섹션 데이터를 계산
4. 프론트는 KPI, 분포 차트, 품질 카드, 알림 카드에 매핑

프론트 반영:

- KPI 카드
- source/status/routing/risk/sentiment/pattern risk 시각화
- coverage 요약
- quality watch 목록
- alert 패널

#### B. 주간 리포트 미리보기

흐름:

1. 프론트가 `GET /reports/weekly?days=7`
2. 백엔드가 `run_weekly_report_workflow(7)` 수행
3. `report` 내용을 반환
4. 프론트는 `narrative_insights`, `delivery_logs` 등을 weekly 탭과 briefing 블록에 표시

프론트 반영:

- weekly highlights
- delivery status
- AI briefing 블록 일부

#### C. 티켓 목록

흐름:

1. 프론트가 `GET /tickets`
2. 백엔드는 기간/상태/리스크/라우팅/소스 필터를 적용해 티켓 목록 반환
3. 목록에는 최신 분석/draft/response id가 함께 포함된다

프론트 반영:

- recent tickets
- weekly review tickets
- 검색/필터 대상 리스트

#### D. 티켓 상세

흐름:

1. 프론트가 `GET /tickets/{ticket_id}`
2. 백엔드는 아래 정보를 한 번에 조회

반환 묶음:

- `ticket`
- `analyses`
- `drafts`
- `evidence_docs`
- `safety_results`
- `final_responses`
- `notifications`
- `voc_feedback`
- `payment_logs`
- `refund_logs`
- `item_delivery_logs`
- `gacha_logs`
- `admin_event_logs`

프론트 반영:

- 우측 Ticket Detail
- Analysis / Draft / Final
- Evidence / VOC

현재 프론트는 이 중 일부만 표면에 올린다. 그러나 API는 훨씬 넓은 운영 데이터를 이미 제공한다.

### 3.3 백엔드에는 있지만 프론트에서 직접 안 쓰는 부분

현재 프론트가 호출하지 않는 대시보드 API:

| 백엔드 API | 연결 로직 | 상태 |
| --- | --- | --- |
| `GET /summary/overview` | `run_dashboard_workflow("overview", days)` | 미사용 |
| `GET /summary/risk` | `run_dashboard_workflow("risk", days)` | 미사용 |
| `GET /summary/quality` | `run_dashboard_workflow("quality", days)` | 미사용 |
| `GET /reports/weekly/pdf` | `run_weekly_report_workflow(..., render_pdf=True)` | 미사용 |
| `POST /reports/weekly/slack` | `run_weekly_report_workflow(..., send_to_slack=True)` | 미사용 |
| `POST /reports/weekly/slack/now` | 기본 Slack 채널 즉시 발송 | 미사용 |

현재 상세 API가 주지만 프론트가 덜 쓰는 데이터:

- `voc_feedback`
- `payment_logs`
- `refund_logs`
- `item_delivery_logs`
- `gacha_logs`
- `admin_event_logs`
- `notifications`의 상세 실패 사유

### 3.4 연결 상태 요약

- 연결 완료: 통합 summary, weekly preview, 티켓 목록, 티켓 상세
- 미연결: summary 개별 엔드포인트, weekly PDF, Slack 발송, 상세 운영 로그의 시각화

## 4. 시스템별 결론

### Chatbot

- 프론트는 로그인, 서버 목록, 티켓 이력, 챗봇 답변까지 연결됨
- 백엔드 내부 세부 추론 상태는 아직 화면에 거의 안 드러남

### CS Auto

- 프론트는 operation workflow의 핵심 수동 검수 루프를 거의 전부 사용 중
- 현재 세 시스템 중 “백엔드 로직이 프론트 행동으로 가장 직접 연결된” 앱

### Dashboard

- 프론트는 요약/리포트/상세 조회를 넓게 연결함
- 다만 PDF 발행, Slack 발송, 결제/VOC/가챠/운영 로그 시각화는 아직 미연결

## 5. 다음 연결 우선순위

우선순위 기준은 “백엔드에 이미 있고 프론트에서 바로 쓸 수 있는 것”이다.

1. `dashboard`
   `GET /reports/weekly/pdf`, `POST /reports/weekly/slack`, `POST /reports/weekly/slack/now`를 버튼으로 연결
2. `dashboard`
   상세 패널에 `voc_feedback`, `payment_logs`, `refund_logs`, `admin_event_logs` 섹션 추가
3. `chatbot`
   `run_chatbot()`의 safety/routing 세부 결과를 FAQ 패널 또는 debug panel에 시각화
4. `cs_auto`
   review log, notification log, multi-draft history를 더 명확한 timeline으로 노출
