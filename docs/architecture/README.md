# Architecture Docs

이 폴더는 시스템 구조를 설명하는 문서를 둡니다.

현재 프로젝트는 하나의 앱이 아니라 다음 3개 실행 축을 가집니다.

- 챗봇 응답
- 운영 배치 처리
- 운영 인사이트 Deep Agent

관련 문서는 아래 순서로 읽으면 됩니다.

- `system-overview.md`: 전체 시스템 개요
- `chatbot.md`: 실시간 문의 처리 흐름
- `operation_batch.md`: 배치 수집/분석/검토 흐름
- `operation_insight.md`: 운영 리포트와 Deep Agent 흐름
- `data-layer.md`: DB, RAG, 로그 조회 계층
- `safety-layer.md`: 검토와 자동 응답 제한 규칙
- `human-in-the-loop.md`: 운영자 승인/수정 프로세스
