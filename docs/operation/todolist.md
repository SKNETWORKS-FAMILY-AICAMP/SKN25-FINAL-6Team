# Operation 발전 Todo List

## P0. 운영 사용성/안정성



- [ ] 워크플로우 실행 API를 추가한다.
  - 현재 API는 초안 검수 중심이며 `build_operation_graph().invoke()`를 호출하는 엔드포인트가 없다.
  - 예: `POST /tickets/{ticket_id}/run-workflow`
  - 중복 실행, 이미 closed 상태, 긴급 알림 상태에 대한 idempotency 규칙이 필요하다.

- [ ] 재시도 상한을 실제 라우팅에 반영한다.
  - `OperationState`에 `retry_count`, `max_retries`가 있지만 `retry_routing_node`에서 상한을 검사하지 않는다.
  - 상한 초과 시 `urgent_alert_node` 또는 사람 검수 대기로 전환하는 정책이 필요하다.

- [ ] 반려 API와 워크플로우 재생성 흐름을 연결한다.
  - `POST /drafts/{draft_id}/reject`는 티켓을 `pending`으로 바꾸지만 새 초안을 생성하지 않는다.
  - 반려 사유를 다음 `OperationState.metadata.retry_reason` 또는 분석 프롬프트에 반영하는 흐름이 필요하다.

## P1. 답변 품질/RAG

- [ ] RAG 검색을 실제 hybrid retrieval로 개선한다.
  - 현재 구현은 PostgreSQL `to_tsvector`와 `ILIKE` 중심이다.
  - 문서 임베딩 컬럼이 있다면 vector similarity를 추가하고, BM25/keyword score와 결합한다.

- [ ] 근거 부족 시 답변 발행 조건을 강화한다.
  - `route_after_save_draft`는 근거가 없어도 바로 안전성 검수로 이동한다.
  - 문의 유형별 최소 근거 수, 필수 문서 category, DB 컨텍스트 일치 조건을 정의한다.

- [ ] LLM 응답 후처리 검증을 추가한다.
  - `HumanReviewResponse.decision`은 현재 `str`이며 route 타입과 완전히 묶여 있지 않다.
  - 허용값 외 응답, 빈 초안, 근거 ID 불일치, 과도한 길이 등을 명시적으로 검증한다.

- [ ] 프롬프트 버전 관리를 체계화한다.
  - `answer_draft.prompt_version`은 `"operation-workflow"` 고정이다.
  - 프롬프트 변경 추적을 위해 `operation-workflow-vYYYYMMDD` 같은 버전 규칙을 둔다.

## P1. API/데이터 계약

- [ ] API 응답 모델을 Pydantic으로 명시한다.
  - 현재 대부분 `dict[str, Any]`로 반환한다.
  - UI와 API 사이의 필드 계약을 안정화하려면 response model을 추가한다.

- [ ] API 에러 응답 형식을 표준화한다.
  - 404 draft not found 외 DB 오류, validation 오류, 동시성 충돌, 권한 오류 형식이 명확하지 않다.

- [ ] 검수 로그 metadata를 확장한다.
  - 초안 수정 전/후 diff, 승인 final_text 길이, reject reason, reviewer_id, 요청 trace id를 저장하면 감사 추적성이 좋아진다.

- [ ] 초안 승인 중복 방지 정책을 추가한다.
  - 동일 `draft_id`로 여러 번 approve 호출 시 `final_response`가 중복 생성될 수 있다.
  - `draft_id` unique 제약 또는 API 레벨 idempotency check가 필요하다.

## P2. 워크플로우 관측성

- [ ] `admin_event_logs`와 파일 로그의 역할을 분리한다.
  - 현재 노드 실행 로그는 파일에, 사람 검수 로그는 DB에 저장된다.
  - 운영 대시보드에서 워크플로우 단계별 성공/실패를 보려면 주요 노드 이벤트도 DB 적재를 고려한다.

- [ ] 노드 실패 시 상태 저장 전략을 추가한다.
  - LLM/DB 오류 발생 시 현재 진행 상태가 별도 테이블에 저장되지 않는다.
  - 재시도 가능한 실패와 수동 개입이 필요한 실패를 구분한다.

- [ ] trace id를 도입한다.
  - 단일 티켓에 여러 워크플로우 실행이 있을 때 `analysis_id`, `draft_id`만으로 실행 단위를 묶기 어렵다.

## P2. 테스트

- [ ] FastAPI 엔드포인트 테스트를 추가한다.
  - `/tickets`, `/tickets/{ticket_id}`, `/drafts/{draft_id}/approve`, reject/edit 경로를 fake DB로 검증한다.

- [ ] Streamlit 컴포넌트 레벨 테스트 또는 최소 스냅샷 검증을 추가한다.
  - 인코딩 깨짐, 버튼 key 충돌, 필수 필드 누락에 취약하다.

- [ ] 위험 케이스 테스트를 추가한다.
  - `risk_level=critical`
  - safety policy violation
  - retrieved docs empty
  - human review reject retry loop
  - duplicate approve

## P3. 코드 정리

- [ ] `nodes.py`를 책임별 모듈로 분리한다.
  - 현재 DB 조회, LLM 호출, 저장, 라우터, 로깅이 한 파일에 모여 있다.
  - 후보 분리: `repository.py`, `llm_nodes.py`, `routers.py`, `logging.py`

- [ ] Mermaid 문서를 실제 그래프와 동기화한다.
  - `docs/operation/architecture/langgraph.mmd`의 일부 엣지는 현재 `graph.py`와 다르다.
  - `build_operation_graph(compile_graph=False)`에서 문서를 생성하는 스크립트를 두면 drift를 줄일 수 있다.

- [ ] `save_final_edit_node`의 DB 저장 책임을 명확히 한다.
  - 현재 이름은 저장처럼 보이지만 실제 DB write는 없고 상태만 업데이트한다.
  - 이름을 바꾸거나 수정 이력을 별도 테이블에 저장한다.
