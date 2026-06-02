아래처럼 **중복 설명 줄이고, 테스트 순서를 먼저 보이게** 정리하면 가독성이 좋아집니다. 기존 문서는 Swagger UI에서 FastAPI API를 수동 테스트하는 가이드입니다. 

````markdown
# cs_auto API Web Manual Test Guide

## 1. 목적

이 문서는 `apps/cs_auto/backend/api/main.py`에 정의된 FastAPI API를  
브라우저의 Swagger UI에서 직접 테스트하는 방법을 정리한 문서입니다.

기본 테스트 흐름은 다음과 같습니다.

1. FastAPI 서버 실행
2. Swagger UI 접속
3. API 직접 호출
4. HTTP 상태 코드와 응답 Body 확인

---

## 2. 서버 실행

아래 명령어를 실행합니다.

```bash
cd C:\SKN25-FINAL-6Team\apps\cs_auto\backend
python -m uvicorn api.main:app --host 127.0.0.1 --port 18000
````

서버가 정상적으로 실행되면 해당 터미널은 닫지 않고 유지합니다.

---

## 3. Swagger UI 접속

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:18000/docs
```

---

## 4. 필수 사전 확인: Health Check

### Endpoint

```http
GET /health
```

### 테스트 방법

1. Swagger UI에서 `GET /health` 선택
2. `Try it out` 클릭
3. `Execute` 클릭

### 기대 결과

```json
{
  "status": "ok"
}
```

| 항목            | 기대값                |
| ------------- | ------------------ |
| Status Code   | `200`              |
| Response Body | `{"status": "ok"}` |

`GET /health`가 실패하면 다른 API 테스트를 진행하지 말고 서버 실행 상태부터 확인합니다.

---

## 5. Admin Login 테스트

### Endpoint

```http
POST /auth/admin/login
```

### Request Body

```json
{
  "login_id": "your-admin-id",
  "password": "your-admin-password"
}
```

### 성공 응답

| 항목            | 기대값            |
| ------------- | -------------- |
| Status Code   | `200`          |
| login_success | `true`         |
| admin_id      | `null`이 아니어야 함 |

### 로그인 실패 응답

| 항목            | 기대값     |
| ------------- | ------- |
| Status Code   | `200`   |
| login_success | `false` |

로그인 실패도 HTTP `401`이 아니라 `200`으로 반환됩니다.
실패 여부는 `login_success` 값으로 판단합니다.

---

## 6. Ticket 목록 조회 테스트

### Endpoint

```http
GET /tickets
```

### Query Parameter 예시

| 파라미터        | 예시값       |
| ----------- | --------- |
| limit       | `5`       |
| status      | `pending` |
| assignee_id | `admin01` |

### 요청 예시

```http
GET /tickets?limit=5
GET /tickets?status=human_review_pending&limit=5
GET /tickets?assignee_id=admin01&limit=5
```

### 기대 결과

| 항목            | 기대값    |
| ------------- | ------ |
| Status Code   | `200`  |
| Response Body | 리스트 형태 |

각 Ticket 항목에는 아래 필드가 포함될 수 있습니다.

```text
ticket_id
title
status
assignee_id
draft_id
```

---

## 7. Ticket 상세 조회 테스트

### Endpoint

```http
GET /tickets/{ticket_id}
```

## 7-1. 존재하는 Ticket 조회

### 테스트 방법

1. `GET /tickets`에서 실제 `ticket_id` 확인
2. `GET /tickets/{ticket_id}`에 해당 ID 입력
3. `Execute` 클릭

### 기대 결과

| 항목          | 기대값   |
| ----------- | ----- |
| Status Code | `200` |

응답에는 아래 정보가 포함될 수 있습니다.

```text
ticket
analyses
drafts
evidence_docs
safety_results
final_responses
notifications
review_logs
```

## 7-2. 존재하지 않는 Ticket 조회

존재하지 않는 큰 숫자의 `ticket_id`를 입력합니다.

### 기대 결과

| 항목            | 기대값                   |
| ------------- | --------------------- |
| Status Code   | `404`                 |
| Response Body | `ticket not found` 포함 |

---

## 8. Ticket 담당자 배정 테스트

### Endpoint

```http
POST /tickets/{ticket_id}/assign
```

### Request Body

```json
{
  "reviewer_id": "1"
}
```

### 기대 결과

```json
{
  "ticket_id": 186,
  "assignee_id": "1"
}
```

| 항목          | 기대값             |
| ----------- | --------------- |
| Status Code | `200`           |
| ticket_id   | 요청한 Ticket ID   |
| assignee_id | 요청한 reviewer_id |

### 검증 방법

담당자 배정 후 아래 API로 다시 확인합니다.

```http
GET /tickets/{ticket_id}
GET /tickets?assignee_id=admin01
```

---

## 9. Workflow 실행 테스트

### Endpoint

```http
POST /tickets/{ticket_id}/run-workflow
```

### 테스트 조건

아직 처리 가능한 실제 `ticket_id`를 사용합니다.

### 성공 응답

| 항목          | 기대값   |
| ----------- | ----- |
| Status Code | `200` |

응답에는 아래 필드가 포함될 수 있습니다.

```text
status
draft_id
analysis_id
response_id
final_answer
```

### 가능한 status 값

```text
closed
human_review_pending
urgent_alert_pending
```

### 충돌 응답

아래 상태의 Ticket은 Workflow 실행이 제한될 수 있습니다.

```text
closed
urgent_alert_pending
workflow_running
```

| 항목          | 기대값   |
| ----------- | ----- |
| Status Code | `409` |

---

## 10. Draft 검수 테스트

Draft 테스트에는 유효한 `draft_id`가 필요합니다.
`GET /tickets/{ticket_id}` 응답에서 `draft_id`를 확인한 뒤 진행합니다.

---

## 10-1. Draft 수정

### Endpoint

```http
PATCH /drafts/{draft_id}
```

### Request Body

```json
{
  "draft_text": "Updated answer text",
  "reviewer_id": "admin01",
  "reason": "manual edit"
}
```

### 기대 결과

| 항목          | 기대값                    |
| ----------- | ---------------------- |
| Status Code | `200`                  |
| decision    | `edited`               |
| status      | `human_review_pending` |

---

## 10-2. Draft 승인

### Endpoint

```http
POST /drafts/{draft_id}/approve
```

### Request Body

```json
{
  "final_text": "Final approved answer",
  "reviewer_id": "admin01",
  "reason": "approved by reviewer"
}
```

### 성공 응답

| 항목          | 기대값        |
| ----------- | ---------- |
| Status Code | `200`      |
| decision    | `approved` |
| status      | `closed`   |

### 충돌 응답

아래 상황에서는 `409 Conflict`가 발생할 수 있습니다.

```text
Draft already approved
Draft is stale
Ticket is already in a blocked or running state
```

---

## 10-3. Draft 재생성

### Endpoint

```http
POST /drafts/{draft_id}/regenerate
```

### Request Body

```json
{
  "reason": "Need a better answer",
  "reviewer_id": "admin01"
}
```

### 성공 응답

| 항목          | 기대값          |
| ----------- | ------------ |
| Status Code | `200`        |
| decision    | `regenerate` |

재생성 성공 시 새로운 Workflow 결과가 반환됩니다.

### 충돌 응답

아래 상황에서는 `409 Conflict`가 발생할 수 있습니다.

```text
Draft already approved
Draft is not the latest draft
Ticket is already workflow_running
```

---

## 11. 최소 테스트 순서

가장 짧게 핵심 기능만 확인하려면 아래 순서로 테스트합니다.

```text
1. GET /health
2. POST /auth/admin/login
3. GET /tickets
4. GET /tickets/{ticket_id}
5. POST /tickets/{ticket_id}/assign
6. POST /tickets/{ticket_id}/run-workflow
```

Draft가 존재한다면 아래 중 하나를 추가로 테스트합니다.

```text
7. PATCH /drafts/{draft_id}
8. POST /drafts/{draft_id}/approve
9. POST /drafts/{draft_id}/regenerate
```

---

## 12. 실패 시 확인 순서

API 호출이 실패하면 아래 순서로 확인합니다.

| 순서 | 확인 항목                                                                    |
| -- | ------------------------------------------------------------------------ |
| 1  | uvicorn 서버가 계속 실행 중인가?                                                   |
| 2  | `GET /health`가 `200`을 반환하는가?                                             |
| 3  | 현재 DB에 존재하는 `ticket_id` 또는 `draft_id`를 사용했는가?                            |
| 4  | Ticket 상태가 이미 `closed`, `urgent_alert_pending`, `workflow_running`은 아닌가? |
| 5  | Draft가 이미 승인되었거나 최신 Draft가 아닌 상태는 아닌가?                                   |
| 6  | 서버 터미널에 Python traceback이 출력되었는가?                                        |

---

## 13. 상태 코드 기준

| Status Code | 의미                       |
| ----------- | ------------------------ |
| `200`       | 요청 성공                    |
| `404`       | Ticket 또는 Draft를 찾을 수 없음 |
| `409`       | 현재 상태상 요청 처리 불가          |
| `422`       | 요청 Body 또는 파라미터 형식 오류    |

---

## 14. 참고 사항

* Swagger UI는 브라우저에서 API를 가장 쉽게 테스트할 수 있는 화면입니다.
* 로그인 실패는 `401`이 아니라 `200`과 `login_success: false`로 반환됩니다.
* 존재하지 않는 Ticket 또는 Draft는 `404`를 반환해야 합니다.
* 이미 처리된 Draft나 잘못된 상태 전이는 `409`를 반환해야 합니다.

```

## 바꾼 방향

- **테스트 순서 중심**으로 재배치
- `Endpoint / Request Body / 기대 결과 / 실패 케이스` 구조로 통일
- 긴 문장을 표와 코드블록으로 분리
- `404`, `409`, `422` 같은 상태 코드를 마지막에 한 번에 정리
- Swagger에서 실제로 따라 하기 쉽도록 단계별 문장 유지
```
