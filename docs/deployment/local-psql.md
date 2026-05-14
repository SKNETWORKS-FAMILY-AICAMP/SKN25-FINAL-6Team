# Local External PostgreSQL

## 목적

초기 개발 단계에서 외부 PostgreSQL 서버와 `psql`만으로 스키마와 데이터를 검증하기 위한 문서입니다.

## 기본 원칙

- `DATABASE_URL` 사용
- 코드에서 호스트 하드코딩 금지
- SQL 파일로 스키마 반영

## 기본 예시

```bash
psql "$DATABASE_URL" -f sql/schema.sql
psql "$DATABASE_URL" -f sql/indexes.sql
psql "$DATABASE_URL" -f sql/seed.sql
```

## 추후 추가할 내용

- PostgreSQL 버전 기준
- 확장 모듈 필요 여부
- 권한 분리 기준
