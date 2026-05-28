# Operation CodeWiki

## 1. 개요

`src/operation`은 게임 고객 문의를 운영자가 검수 가능한 답변 초안으로 전환하는 운영 워크플로우입니다. 핵심은 LangGraph 기반 자동 처리 파이프라인이며, FastAPI는 검수 API를 제공하고 Streamlit은 운영자 UI를 제공합니다.

주요 책임은 다음과 같습니다.

- `qa_ticket`에서 문의와 사용자/계정 메타데이터를 로드한다.
- LLM으로 문의 유형을 분류하고, 유형별 업무 DB 컨텍스트를 조회한다.
- 위험도와 처리 목표를 분석해 일반 답변 흐름 또는 긴급 알림 흐름으로 분기한다.
- RAG 근거 문서를 검색해 답변 초안을 생성하고, 안전성 검수를 수행한다.
- 승인된 답변은 `final_response`에 저장하고 티켓을 `closed`로 변경한다.
- 긴급/정책 위반/고위험 케이스는 `notification_logs`에 운영 알림으로 남긴다.

## 2. 코드 지도

| 경로 | 역할 |
| --- | --- |
| `src/operation/workflow/state.py` | LangGraph 전체 상태와 하위 모델 정의 |
| `src/operation/workflow/prompts.py` | LLM 구조화 응답 모델과 프롬프트 템플릿 |
| `src/operation/workflow/nodes.py` | DB 조회/저장, LLM 호출, 라우터, 노드 로깅 구현 |
| `src/operation/workflow/graph.py` | LangGraph 노드와 조건부 엣지 선언 |
| `src/operation/api/main.py` | 운영자 검수용 FastAPI 엔드포인트 |
| `src/operation/frontend/app.py` | Streamlit 통합 검수 화면 |
| `src/operation/frontend/pages/*` | 문의 목록, 답변 검수, 검수 결과 페이지 |
| `src/operation/frontend/components/*` | 티켓 카드, 답변 패널, 안전성 결과 UI |
| `src/operation/run.py` | FastAPI와 Streamlit을 함께 실행하는 로컬 런처 |
| `tests/operation/*` | 노드 단위 테스트, 전체 그래프 경로 테스트, 그래프 이미지 생성 테스트 |

## 3. 실행 단위

운영 워크플로우의 실행 단위는 `OperationState`입니다. `ticket_id`를 입력으로 받아 다음 상태를 누적합니다.

- 문의 정보: `ticket`, `query_text`
- 라우팅 정보: `query_route`, `target_route`, `approval_route`, `human_decision`
- 업무 컨텍스트: `context`, `context_nodes`
- LLM 산출물: `analysis`, `answer_draft`, `urgent_draft`, `safety_result`, `human_review`
- DB 식별자: `analysis_id`, `draft_id`, `safety_id`, `response_id`
- 최종 결과: `final_answer`, `status`, `errors`, `metadata`

상태 모델은 `extra="allow"`로 설정되어 있어 DB/LLM에서 추가 필드가 들어와도 워크플로우가 깨지지 않도록 설계되어 있습니다.

## 4. 주요 흐름

일반 답변 흐름:

```text
load_ticket
-> query_router
-> {route}_context_node
-> analyze_ticket
-> save_analysis
-> rag_retrieve_node
-> generate_answer_node
-> save_draft_node
-> save_evidence_docs_node 또는 approval_gate_node
-> save_safety_result_node
-> publish_final_answer_node 또는 human_review_node 또는 urgent_alert_node
```

긴급 알림 흐름:

```text
load_ticket
-> query_router
-> {route}_context_node
-> analyze_ticket
-> save_analysis
-> urgent_draft_node
-> save_draft_node
-> urgent_alert_node
```

상세 노드 설명은 [workflow.md](./workflow.md)를 참고합니다.

## 5. 외부 인터페이스

FastAPI는 운영자 UI가 사용할 검수 API를 제공합니다.

- `GET /health`
- `GET /tickets`
- `GET /tickets/{ticket_id}`
- `PATCH /drafts/{draft_id}`
- `POST /drafts/{draft_id}/approve`
- `POST /drafts/{draft_id}/reject`

Streamlit UI는 위 API를 호출해 문의 목록 조회, 최신 분석/초안/근거/안전성 결과 확인, 초안 수정/승인/반려를 수행합니다. 상세는 [api_frontend.md](./api_frontend.md)와 [api_spec.md](./api_spec.md)를 참고합니다.

## 6. 테스트 관점

현재 `tests/operation`은 다음을 검증합니다.

- 노드 단위 테스트: 티켓 로딩, 컨텍스트 병합, LLM 노드 반환값, 라우터 필수 상태 검증
- 전체 그래프 테스트: 일반 승인 경로, 긴급 알림 경로, `RETURNING` 기반 ID 처리
- 그래프 이미지 테스트: LangGraph 구조 PNG 생성

테스트는 실제 DB/LLM 대신 fake DB와 fake structured LLM을 사용해 워크플로우 동작을 고립 검증합니다.

## 7. 개선 방향

우선 개선 과제는 [todolist.md](./todolist.md)에 정리했습니다. 특히 UI 문자열 인코딩 깨짐, API와 워크플로우 검수 흐름의 책임 분리, RAG 검색 품질, 재시도 제한, 운영 감사 로그 확장이 우선순위가 높습니다.
