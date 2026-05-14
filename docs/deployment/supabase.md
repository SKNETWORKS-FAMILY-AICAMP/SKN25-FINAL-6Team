# Supabase

## 목적

PostgreSQL 중심 구조를 추후 Supabase로 이전할 때 참고할 문서입니다.

## 전환 원칙

- 가능하면 `DATABASE_URL` 기반 애플리케이션 구조 유지
- SQL 스키마를 최대한 재사용
- 앱 코드에서 Supabase 종속성 최소화

## 추후 정리할 항목

- 연결 문자열 차이
- `pgvector` 사용 방식
- 인증/스토리지 사용 여부
