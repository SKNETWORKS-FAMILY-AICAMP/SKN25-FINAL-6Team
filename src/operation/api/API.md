# API 명세서 작성 가이드

> 출결 검색 API (`/api/search`)를 기준으로 한 명세서 작성 방법

---

## 1. 명세서 기본 구조

API 하나당 아래 순서로 작성합니다.

```
# {기능명}
### Method & Endpoint
### Query Parameter / Request Body
### Response
### Status
```

---

## 2. Method & Endpoint

HTTP 메서드와 URL 경로를 함께 명시합니다.

```
GET /api/search
```

| 메서드 | 용도 |
|--------|------|
| `GET` | 데이터 조회 |
| `POST` | 데이터 생성 |
| `PUT` | 데이터 전체 수정 |
| `PATCH` | 데이터 부분 수정 |
| `DELETE` | 데이터 삭제 |

> **출결 검색**은 데이터를 조회하므로 `GET`을 사용합니다.

---

## 3. Query Parameter

`GET` 요청에서 URL 뒤에 `?key=value` 형태로 전달하는 값입니다.

**형식**
```
/api/search?id=1&date=2024-10-20
```

**파라미터 목록 작성 방법**

| 파라미터 | 타입 | 필수 여부 | 설명 | 예시 |
|----------|------|-----------|------|------|
| `id` | String | Required | 조회할 학생 ID | `1` |
| `date` | String | Required | 조회할 날짜 (형식: `YYYY-MM-DD`) | `2024-10-20` |

> **주의**: `date`의 형식(`YYYY-MM-DD`)은 반드시 명시해야 합니다.  
> 형식이 다르면 `400` 에러를 반환해야 합니다.

---

## 4. Response

### 4-1. Response Body 테이블 작성 방법

| 컬럼 | 설명 |
|------|------|
| `key` | 응답 JSON의 필드명 |
| `설명` | 해당 필드가 의미하는 것 |
| `value 타입` | 데이터 타입 (`String`, `Number`, `Boolean`, `Array`, `Object`) |
| `옵션` | ENUM일 경우 가능한 값 목록 |
| `Nullable` | `O` = null 가능 / `X` = null 불가 |
| `예시` | 실제 응답 예시 값 |

**작성 예시**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|-----|------|------------|------|----------|------|
| `userId` | 학생 ID | String | | X | `"1"` |
| `name` | 학생 이름 | String | | X | `"HongGilDong"` |
| `grade` | 학년 | Number | | X | `3` |
| `attendanceItems` | 출결 기록 배열 | Array | | X | `[{...}]` |
| `date` | 출결 날짜 | String | | X | `"2024-08-08"` |
| `status` | 출결 상태 | String (ENUM) | `ATTEND` \| `ABSENT` \| `ONLINE` \| `NONE` | X | `"ABSENT"` |
| `reason` | 결석/지각 사유 | String | | O | `"병원"` |

### 4-2. 중첩 구조 표기 방법

`attendanceItems`처럼 배열 안에 객체가 있을 경우, 들여쓰기로 하위 필드를 표현합니다.

```
attendanceItems[]
  ├─ date      : 출결 날짜
  ├─ status    : 출결 상태 (ENUM)
  └─ reason    : 사유 (Nullable)
```

### 4-3. ENUM 작성 방법

가능한 값이 정해진 경우 `옵션` 컬럼에 모두 나열합니다.

```
status 가능한 값:
- ATTEND  : 출석
- ABSENT  : 결석
- ONLINE  : 온라인 출석
- NONE    : 정보 없음
```

### 4-4. Example (응답 예시)

실제 응답 JSON을 작성합니다. 모든 필드가 포함되어야 합니다.

```json
{
  "userId": "1",
  "name": "HongGilDong",
  "grade": 3,
  "attendanceItems": [
    {
      "date": "2024-10-20",
      "status": "ABSENT",
      "reason": "병원"
    },
    {
      "date": "2024-10-21",
      "status": "ATTEND",
      "reason": null
    }
  ]
}
```

> **주의**: `reason`이 `Nullable`이므로 null인 경우도 예시에 포함해야 합니다.

---

## 5. Status Code

요청 결과에 따른 HTTP 상태 코드와 응답 내용을 명시합니다.

| status | 상황 | response content |
|--------|------|-----------------|
| `200` | 조회 성공 | Response Body 반환 |
| `400` | 잘못된 요청 (파라미터 누락 또는 형식 오류) | `{ "error": "id is required" }` |
| `401` | 인증 실패 | `{ "error": "Unauthorized" }` |
| `404` | 해당 id의 학생 없음 | `{ "error": "User not found" }` |
| `500` | 서버 내부 오류 | `{ "error": "Internal server error" }` |

> **중요**: `400` 에러 응답의 Body도 반드시 작성해야 합니다.  
> 클라이언트가 어떤 값을 잘못 보냈는지 알 수 있어야 합니다.

---

## 6. 완성된 명세서 예시

```markdown
# 출결 검색

## Method & Endpoint
GET /api/search

## Query Parameter
`/api/search?id=1&date=2024-10-20`

| 파라미터 | 타입   | 필수 여부 | 설명                          | 예시         |
|----------|--------|-----------|-------------------------------|--------------|
| id       | String | Required  | 조회할 학생 ID                | 1            |
| date     | String | Required  | 조회할 날짜 (YYYY-MM-DD 형식) | 2024-10-20   |

## Response

| key            | 설명        | value 타입    | 옵션                                   | Nullable | 예시           |
|----------------|-------------|---------------|----------------------------------------|----------|----------------|
| userId         | 학생 ID     | String        |                                        | X        | "1"            |
| name           | 학생 이름   | String        |                                        | X        | "HongGilDong"  |
| grade          | 학년        | Number        |                                        | X        | 3              |
| attendanceItems| 출결 기록   | Array         |                                        | X        | [{...}]        |
| date           | 출결 날짜   | String        |                                        | X        | "2024-08-08"   |
| status         | 출결 상태   | String (ENUM) | ATTEND \| ABSENT \| ONLINE \| NONE    | X        | "ABSENT"       |
| reason         | 사유        | String        |                                        | O        | "병원"         |

### Example
{
  "userId": "1",
  "name": "HongGilDong",
  "grade": 3,
  "attendanceItems": [
    {
      "date": "2024-10-20",
      "status": "ABSENT",
      "reason": "병원"
    }
  ]
}

## Status

| status | 상황                  | response content                    |
|--------|-----------------------|-------------------------------------|
| 200    | 조회 성공             | Response Body 반환                  |
| 400    | 파라미터 누락/형식 오류 | { "error": "id is required" }     |
| 404    | 학생 없음             | { "error": "User not found" }      |
| 500    | 서버 오류             | { "error": "Internal server error" }|
```

---

## 7. 참고 파일 목록 (프로젝트 기준)

API 명세서 작성 시 아래 파일들을 순서대로 참고합니다.

### 7-1. API 엔드포인트 정의 (가장 중요)

| 서비스 | 파일 | 내용 |
|--------|------|------|
| Operation | `src/operation/api/main.py` | 티켓 목록·상세·워크플로우 실행·초안 승인/반려/수정 |
| Chatbot | `src/chatbot/api/main.py` | 챗봇 대화 요청/응답 |
| Dashboard | `src/dashboard/api/main.py` | 요약 지표·티켓 목록·주간 보고서·Slack 전송 |

### 7-2. Request / Response 스키마 (ENUM·타입 정보)

| 파일 | 내용 |
|------|------|
| `src/chatbot/schemas.py` | `Category`, `RoutingTarget`, `SafetyAction` ENUM, `ChatRequest`, `ChatResponse` |
| `src/operation/workflow/state.py` | `QueryRoute`, `TargetRoute`, `ApprovalRoute`, `RiskLevel` ENUM, `OperationState` 전체 필드 |

### 7-3. DB 스키마 (응답 필드의 출처 확인)

| 파일 | 내용 |
|------|------|
| `docs/DB/descriptions.md` | 테이블별 컬럼·타입·nullable·FK 전체 명세 |
| `docs/DB/db_info.md` | DB 연결 정보 및 스키마 개요 |
| `docs/DB/migrations/20260521_operation_workflow_identity_defaults.sql` | 최신 스키마 변경 사항 |

### 7-4. 기존 API 명세서 (업데이트 기준)

| 파일 | 내용 |
|------|------|
| `docs/operation/api_spec.md` | Operation API 기존 명세 |
| `docs/chatbot/api_spec.md` | Chatbot API 기존 명세 |
| `docs/dashboard/api_spec.md` | Dashboard API 기존 명세 |
| `docs/operation/api_frontend.md` | 프론트엔드 연동 기준 API 명세 |

### 7-5. 작업 순서

```
1단계  main.py 3개
       └─ 엔드포인트, 파라미터, HTTP 메서드 확인

2단계  schemas.py / state.py
       └─ ENUM 값과 타입 확인

3단계  descriptions.md
       └─ 응답 필드의 Nullable 여부 확인

4단계  기존 api_spec.md와 대조
       └─ 누락·변경된 부분 업데이트
```

---

## 8. 자주 실수하는 부분 체크리스트

- [ ] HTTP 메서드(`GET`, `POST` 등)를 명시했는가?
- [ ] `date` 같은 문자열 필드의 **형식**(`YYYY-MM-DD`)을 명시했는가?
- [ ] ENUM 필드의 **모든 가능한 값**을 나열했는가?
- [ ] `Nullable` 필드는 **null인 경우 예시**도 포함했는가?
- [ ] `400` 에러의 **응답 Body**를 작성했는가?
- [ ] 중첩 구조(`attendanceItems` 내부 필드)를 표로 표현했는가?
- [ ] 성공/실패 **모든 케이스의 Example**이 있는가?
