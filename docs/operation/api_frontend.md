# Operation API 및 Frontend 운영자 가이드

## 1. 운영자 화면의 목표

운영자는 매일 접수된 문의 중 아직 처리되지 않은 항목을 먼저 확인하고, 생성된 답변 초안을 검수합니다. 화면에서 유지해야 하는 핵심 기능은 다음 세 가지입니다.

- 오늘 확인해야 할 문의 목록을 기본으로 보여준다.
- 답변 초안을 운영자가 직접 수정하고 저장할 수 있다.
- 수정된 답변 또는 기존 초안을 승인해 최종 답변으로 발행할 수 있다.

반려 기능도 유지하지만, 현재 반려는 티켓 상태를 `pending`으로 되돌리고 검수 로그를 남기는 역할까지 수행합니다. 반려 후 LangGraph 재생성은 아직 별도 실행 경로가 필요합니다.

## 2. 운영자 사용 흐름

```text
운영자 UI 접속
-> 기본 목록 "오늘 확인할 문의" 확인
-> 문의 카드에서 "상세 확인" 선택
-> 문의 원문, 분석 결과, 안전성 검수, 근거 문서, 답변 초안 확인
-> 답변 초안을 그대로 승인하거나 문구를 수정
-> "수정 저장"으로 초안만 저장하거나 "승인"으로 최종 답변 발행
-> 승인 시 final_response 저장 및 qa_ticket.status = closed
```

## 3. 오늘 확인할 문의 목록

UI 기본 목록은 `GET /tickets/today`를 호출합니다.

기본 조건:

- `qa_ticket.inquiry_created_at`이 DB 서버 `CURRENT_DATE` 범위에 포함된다.
- 기본 상태는 `pending`이다.
- 최신 `answer_draft`와 최신 `ticket_analysis` 요약을 함께 보여준다.

프론트엔드에서는 사이드바의 "문의 목록" 선택값으로 조회 범위를 바꿀 수 있습니다.

| 선택값 | 호출 API | 기본 필터 |
| --- | --- | --- |
| 오늘 확인할 문의 | `GET /tickets/today` | `status=pending` |
| 대기 중 문의 | `GET /tickets` | `status=pending` |
| 종료된 문의 | `GET /tickets` | `status=closed` |
| 전체 문의 | `GET /tickets` | 상태 필터 없음 |

## 4. 검수 기능

### 수정 저장

운영자가 답변 초안 문구를 수정한 뒤 "수정 저장"을 누르면 `PATCH /drafts/{draft_id}`가 호출됩니다.

처리 결과:

- `answer_draft.draft_text`가 수정된다.
- `admin_event_logs`에 `decision=edited` 검수 로그가 남는다.
- 티켓 상태와 최종 답변은 변경하지 않는다.

### 승인

운영자가 "승인"을 누르면 `POST /drafts/{draft_id}/approve`가 호출됩니다.

처리 결과:

- 화면의 편집 텍스트가 `final_text`로 전달된다.
- `final_response`에 최종 답변이 저장된다.
- `qa_ticket.status`가 `closed`로 변경된다.
- `admin_event_logs`에 `decision=approved` 검수 로그가 남는다.

### 반려

운영자가 반려 사유를 입력하고 "반려 실행"을 누르면 `POST /drafts/{draft_id}/reject`가 호출됩니다.

처리 결과:

- `qa_ticket.status`가 `pending`으로 변경된다.
- `admin_event_logs`에 `decision=rejected`와 반려 사유가 남는다.
- 현재 구현에서는 워크플로우 재생성을 자동으로 실행하지 않는다.

## 5. 화면 구성

| 영역 | 설명 |
| --- | --- |
| 사이드바 | API URL, 검수자 ID, 문의 목록 범위, 조회 개수 설정 |
| 왼쪽 목록 | 오늘 확인할 문의 또는 선택한 범위의 문의 카드 |
| 오른쪽 상세 | 문의 원문, 상태/채널/닉네임/계정, 분석 결과, 안전성 결과, 근거 문서, 답변 초안 |
| 답변 패널 | 답변 수정, 수정 저장, 승인, 반려 실행 |

## 6. 관련 코드

| 경로 | 역할 |
| --- | --- |
| `src/operation/api/main.py` | `/tickets/today`, `/tickets`, 상세 조회, 초안 수정/승인/반려 API |
| `src/operation/frontend/app.py` | 오늘 문의 기본 목록과 상세 검수 화면 |
| `src/operation/frontend/components/ticket_card.py` | 문의 카드 |
| `src/operation/frontend/components/answer_panel.py` | 수정 저장/승인/반려 액션 |
| `src/operation/frontend/components/safety_result_box.py` | 안전성 검수 결과 표시 |

## 7. 현재 한계

- 날짜 기준은 애플리케이션 서버가 아니라 DB 서버의 `CURRENT_DATE`를 따른다.
- 승인 중복 방지를 위한 `draft_id` 기준 idempotency check는 아직 없다.
- 반려 후 재생성은 API에서 직접 트리거하지 않는다.
- API 응답은 아직 대부분 `dict[str, Any]`라 명시적인 response model 보강이 필요하다.
