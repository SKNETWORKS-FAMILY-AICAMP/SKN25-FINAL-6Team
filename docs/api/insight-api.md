# Insight API

## 목적

운영 리포트, 인사이트, FAQ 후보, 라우팅 개선안 조회를 위한 API 초안입니다.

## 후보 엔드포인트

- `GET /api/insights`
- `GET /api/insights/{insight_id}`
- `GET /api/reports/weekly`
- `GET /api/reports/incidents`
- `POST /api/reports/generate`
- `GET /api/faq-candidates`
- `GET /api/router-improvements`

## 추후 정의할 항목

- 조회 기간 파라미터
- 리포트 생성 트리거 방식
- 운영 권한 범위
