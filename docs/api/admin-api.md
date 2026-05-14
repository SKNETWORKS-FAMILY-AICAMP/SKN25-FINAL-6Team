# Admin API

## 목적

운영자가 검토 대기 문의를 확인하고 승인/수정/반려하기 위한 API 초안입니다.

## 후보 엔드포인트

- `GET /api/admin/tickets`
- `GET /api/admin/tickets/{ticket_id}`
- `POST /api/admin/tickets/{ticket_id}/approve`
- `POST /api/admin/tickets/{ticket_id}/edit-approve`
- `POST /api/admin/tickets/{ticket_id}/reject`
- `POST /api/admin/tickets/{ticket_id}/regenerate`

## 추후 정의할 항목

- 상태 전이 규칙
- 운영자 권한 모델
- 수정 이력 저장 방식
