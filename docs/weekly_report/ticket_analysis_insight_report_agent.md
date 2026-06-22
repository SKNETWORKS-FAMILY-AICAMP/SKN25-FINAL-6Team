# Ticket Analysis Insight Report Agent

## 상태

이 문서는 예전의 “전용 insight 페이지 + 대시보드 에이전트” 설계 초안을 대체한다.

현재 저장소에는 다음이 존재한다.

- 전용 insight 페이지: 없음
- `ticket_analysis` 전용 대시보드 API: 없음
- 주간 리포트 배치: 있음

즉, 현재 구현은 **`ticket_analysis`와 `insight`를 읽어 주간 리포트를 만드는 배치 파이프라인**이지, 별도 insight 화면을 제공하는 에이전트가 아니다.

## 현재 구현 요약

현재 `apps/weekly_report`에서 `ticket_analysis` 관련 처리는 아래처럼 이뤄진다.

1. `db.analysis.fetch_analysis_rows()`가 `ticket_analysis` + `qa_ticket` + `community_users` + 최신 `insight`를 읽는다.
2. `db.metrics.fetch()`가 커버리지/카테고리 분포를 계산한다.
3. `build.review_rows.pick_review_rows()`가 검토할 행을 고른다.
4. `ai.row_interpret.generate_review_row_interpretations()`가 선택 행의 해석을 만든다.
5. `build.payload.build_report_payload()`가 PDF/Slack용 payload를 만든다.

## 문서 기준점

현재 상태를 설명하는 문서는 아래를 기준으로 본다.

- `docs/weekly_report/architecture.md`
- `docs/weekly_report/metrics.md`
- `docs/weekly_report/prd.md`

## 더 이상 유효하지 않은 전제

아래 전제는 현재 코드와 맞지 않는다.

- `ticket_analysis` 전용 화면이 존재한다
- `/summary/*` 또는 `/tickets*` API가 `apps/weekly_report`에 구현돼 있다
- Streamlit 대시보드가 현재 주 실행 경로다
- 별도 에이전트가 insight 페이지를 렌더링한다

필요 시 이 파일은 향후 다시 상세 설계 문서로 확장할 수 있지만, 현재는 아카이브 성격의 정정 문서로 유지한다.
