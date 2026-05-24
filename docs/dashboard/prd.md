# Dashboard PRD

## 1. 문서 목적

이 문서는 `docs/chatbot/prd.md`와 `docs/operation/prd.md`를 바탕으로 운영자, 상담원, 품질 관리자, 리스크 담당자가 확인하는 운영 대시보드의 요구사항을 정의한다.

대시보드는 챗봇과 운영배치가 생성한 문의, 분석, 답변 초안, 근거 문서, 안전성 검증, 최종 응답, 알림, VOC 데이터를 통합 조회한다. DB와 용어는 `docs/DB/descriptions.md`의 PostgreSQL `public` 스키마를 기준으로 하며, 기존 테이블과 충돌하는 신규 테이블명이나 컬럼명을 정의하지 않는다.

## 2. 참조 문서

| 문서 | 반영 범위 |
| --- | --- |
| `docs/chatbot/prd.md` | 챗봇 문의 유입, 자동 응답, 상담원 패싱, 만족도, 챗봇 운영 지표 |
| `docs/operation/prd.md` | 운영배치 처리 단계, Human-in-the-loop, 운영 인사이트, Observability, 운영자 검수 |
| `docs/DB/descriptions.md` | 실제 PostgreSQL 테이블, 컬럼, 관계 |
| `docs/dashboard/architecture.md` | Dashboard API, summary pipeline, Streamlit 구조 |
| `docs/dashboard/api_spec.md` | `/summary/*`, `/tickets`, `/tickets/{ticket_id}` 응답 기준 |
| `docs/dashboard/metrics.md` | 지표 산식과 조회 기간 기준 |
| `docs/dashboard/screen_design.md` | 운영자 화면 구조와 화면별 표시 기준 |

## 3. 범위

### 3.1 포함 범위

- 운영 현황 요약: 문의 수, 대기/종료, 오늘 접수, 응답률, 분석/초안 커버리지
- 리스크 분석: 위험도, 감성, 패턴 위험도, 안전성 점수, 고위험 후보
- 응답 품질: 초안, 근거 문서, 안전성 검증, 최종 응답, 알림 상태
- 티켓 목록과 상세: 문의 원문, 계정 요약, 분석 결과, 답변 초안, 근거, 안전성, 최종 응답, 알림, VOC
- 운영자 검수 큐 확인: `human_review`, `urgent_alert`, 낮은 사실성, 높은 환각 점수 등 검수 우선순위
- 운영 알림 현황: Slack/Discord 등 알림 발송 상태와 실패 사유 조회

### 3.2 제외 범위

- 대시보드 자체의 별도 업무 테이블 생성
- 대시보드에서 직접 결제, 환불, 아이템 지급을 실행하는 기능
- 대시보드에서 LLM 분석 또는 답변 생성을 직접 수행하는 기능
- Vector DB 임베딩 생성 또는 문서 수집 파이프라인

후속 조치가 필요한 경우 대시보드는 기존 `operation` 검수 API 또는 운영자 워크플로우로 이동할 수 있는 맥락을 제공한다.

## 4. 사용자와 권한

| 사용자 | 주요 목적 | 권한 기준 |
| --- | --- | --- |
| 운영 관리자 | 전체 문의량, 처리 상태, 장애성 증가 여부 확인 | 전체 운영 지표 조회 |
| 상담원/검수자 | `human_review` 문의와 답변 초안 검토 | 담당 범위 티켓 상세 조회, 민감정보 제한 표시 |
| 리스크 담당자 | HIGH/critical 문의, 부정 감성, 정책 위반 위험 확인 | 리스크 요약과 고위험 후보 조회 |
| 품질 관리자 | 답변 승인율, 초안 수정률, 근거 첨부율, Safety 점수 확인 | 응답 품질 지표 조회 |
| 시스템 관리자 | API 상태, 알림 실패, DB 조회 오류 확인 | 운영 로그와 실패 이력 조회 |

## 5. 데이터 원칙

| 원칙 | 내용 |
| --- | --- |
| 실제 DB 기준 | 테이블명은 `docs/DB/descriptions.md`의 실제 이름인 `qa_ticket`, `ticket_analysis`, `answer_draft` 등을 사용한다. |
| 읽기 중심 | 대시보드 요약과 상세 조회는 기본적으로 기존 테이블을 읽는다. |
| 최신 레코드 기준 | 티켓별 최신 분석/초안/응답은 `analyzed_at`, `created_at`, `checked_at`, 각 PK의 내림차순으로 선택한다. |
| 날짜 필터 기준 | 기간 필터는 `qa_ticket.inquiry_created_at >= window_start`를 기본으로 한다. |
| 개인정보 최소 노출 | `raw_query`, `email`, `uid`, `transaction_id`, `refund_reason` 등은 역할에 따라 마스킹하거나 상세 권한이 있을 때만 표시한다. |
| 상태값 정합성 | `qa_ticket.status`, `ticket_analysis.routing_target`, `safety_results.safety_action`, `final_response.safety_action`을 혼용하지 않고 각 의미에 맞게 표시한다. |

## 6. 주요 데이터 소스

| 영역 | 테이블 | 사용 목적 |
| --- | --- | --- |
| 문의 원천 | `qa_ticket` | 티켓 수, 상태, 채널, 문의 원문, 접수 시각 |
| 사용자/계정 | `community_users`, `game_accounts` | 닉네임, 계정 상태, 서버, 진행도 요약 |
| 분석 | `ticket_analysis` | 카테고리, 위험도, 감성, 라우팅 대상, 요약 |
| 답변 | `answer_draft`, `final_response` | 답변 초안, 최종 응답, 프롬프트 버전, 응답 시각 |
| 근거 | `evidence_docs`, `documents`, `documents_chunks` | 근거 문서, 관련도, 원문 추적 |
| 안전성 | `safety_results` | 환각, 유해성, 정책 위반, 사실성, 검증 액션 |
| 운영 로그 | `admin_event_logs`, `failed_queries`, `notification_logs` | 운영 이벤트, 처리 실패, 알림 발송 상태 |
| 업무 로그 | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs` | 결제, 환불, 지급, 가챠 문의 상세 근거 |
| 인사이트/VOC | `insight`, `voc_feedback` | 반복 이슈, 패턴 위험도, 고객의 소리 |

## 7. 기능 요구사항

| 분류 | 대분류 | 중분류 | 요구사항 ID | 기능 설명 | 추가 설명 |
| --- | --- | --- | --- | --- | --- |
| 기능 | Dashboard Access | 인증된 운영자 접근 | FR-DASH-ACS-001 | 시스템은 인증된 운영자만 대시보드에 접근할 수 있어야 한다. | 상담원, 운영자, 관리자 역할에 따라 조회 범위를 제한한다. |
| 기능 | Dashboard Access | 역할별 개인정보 표시 | FR-DASH-ACS-002 | 시스템은 역할에 따라 개인정보와 결제 식별자의 표시 범위를 달리해야 한다. | `email`, `uid`, `transaction_id`, `refund_reason`, `raw_query`는 최소 권한 기준으로 표시한다. |
| 기능 | Dashboard Access | 조회 전용 기본 동작 | FR-DASH-ACS-003 | 시스템은 대시보드 요약, 목록, 상세 화면을 읽기 전용으로 제공해야 한다. | 결제/환불/지급 실행은 operation 검수 흐름에서 처리한다. |
| 기능 | 운영 현황 | 핵심 KPI 제공 | FR-DASH-OVR-001 | 운영자는 전체 문의, 대기 문의, 종료 문의, 오늘 접수 건수를 확인할 수 있어야 한다. | `qa_ticket` 기준 집계, 기본 기간은 30일이다. |
| 기능 | 운영 현황 | 응답 처리 지표 제공 | FR-DASH-OVR-002 | 운영자는 응답률, 평균 응답 지연, 분석 커버리지, 초안 커버리지를 확인할 수 있어야 한다. | `qa_ticket`, `ticket_analysis`, `answer_draft`, `final_response` 기반 산출 |
| 기능 | 운영 현황 | 분포 차트 제공 | FR-DASH-OVR-003 | 운영자는 접수 채널, 상태, 라우팅 대상 분포를 확인할 수 있어야 한다. | `source_type`, `status`, 최신 `ticket_analysis.routing_target` 기준 |
| 기능 | 운영 현황 | 최근 문의 목록 제공 | FR-DASH-OVR-004 | 운영자는 최근 문의 목록을 상태, 채널, 위험도, 라우팅 대상과 함께 확인할 수 있어야 한다. | `/tickets` API와 연계하며 기본 50건, 최대 200건을 제공한다. |
| 기능 | 운영 현황 | 기간 필터 제공 | FR-DASH-OVR-005 | 운영자는 1일부터 365일까지 조회 기간을 조정할 수 있어야 한다. | `qa_ticket.inquiry_created_at` 기준으로 필터링한다. |
| 기능 | 리스크 분석 | 위험도 분포 제공 | FR-DASH-RISK-001 | 리스크 담당자는 문의 분석 위험도와 인사이트 위험도 분포를 확인할 수 있어야 한다. | `ticket_analysis.risk_level`, `insight.risk_level`, `insight.pattern_risk_level` 기준 |
| 기능 | 리스크 분석 | 감성 분포 제공 | FR-DASH-RISK-002 | 리스크 담당자는 문의 감성 분포와 부정 감성 증가 여부를 확인할 수 있어야 한다. | `ticket_analysis.sentiment`, `insight.sentiment`, `voc_feedback.sentiment` 활용 |
| 기능 | 리스크 분석 | 안전성 점수 요약 | FR-DASH-RISK-003 | 시스템은 평균 환각, 유해성, 정책 위반, 사실성 점수를 표시해야 한다. | `safety_results`의 `hallucination_score`, `toxicity_score`, `policy_violation_score`, `factuality_score` 기준 |
| 기능 | 리스크 분석 | 고위험 후보 목록 | FR-DASH-RISK-004 | 리스크 담당자는 HIGH 또는 critical 후보 티켓을 우선순위로 확인할 수 있어야 한다. | 최신 분석 또는 인사이트 패턴 위험도 기준으로 정렬한다. |
| 기능 | 리스크 분석 | 안전성 경고 플래그 | FR-DASH-RISK-005 | 시스템은 threshold를 초과한 안전성 지표에 경고를 표시해야 한다. | 기본 threshold는 `docs/dashboard/metrics.md`의 Alert Threshold를 따른다. |
| 기능 | 응답 품질 | 초안 생성 현황 | FR-DASH-QLT-001 | 품질 관리자는 생성된 답변 초안 수와 티켓 대비 초안 생성률을 확인할 수 있어야 한다. | `answer_draft`와 `qa_ticket` 기준 산출 |
| 기능 | 응답 품질 | 근거 첨부 현황 | FR-DASH-QLT-002 | 품질 관리자는 근거 문서가 연결된 초안 비율과 평균 관련도를 확인할 수 있어야 한다. | `evidence_docs.relevance_score`, `retrieval_rank` 기준 |
| 기능 | 응답 품질 | 최종 응답 현황 | FR-DASH-QLT-003 | 품질 관리자는 최종 응답 수, 최종 응답률, 평균 최종 지연을 확인할 수 있어야 한다. | `final_response.created_at - qa_ticket.inquiry_created_at` 기준 |
| 기능 | 응답 품질 | 품질 점검 후보 | FR-DASH-QLT-004 | 품질 관리자는 낮은 사실성 또는 높은 환각 점수의 초안을 우선 점검할 수 있어야 한다. | `safety_results`와 `answer_draft` 조인 기준 |
| 기능 | 응답 품질 | 알림 상태 분포 | FR-DASH-QLT-005 | 운영자는 알림 성공, 실패, 대기 상태 분포를 확인할 수 있어야 한다. | `notification_logs.status`, `error_message`, `error_category` 기준 |
| 기능 | 티켓 탐색 | 티켓 목록 조회 | FR-DASH-TCK-001 | 운영자는 상태, 채널, 위험도, 라우팅 대상 기준으로 티켓을 탐색할 수 있어야 한다. | 목록 API는 최신 분석, 최신 초안, 최신 최종 응답 메타데이터를 포함한다. |
| 기능 | 티켓 탐색 | 티켓 상세 조회 | FR-DASH-TCK-002 | 운영자는 특정 티켓의 문의, 분석, 초안, 근거, 안전성, 최종 응답, 알림, VOC를 한 화면에서 확인할 수 있어야 한다. | `/tickets/{ticket_id}` API 응답 구조를 따른다. |
| 기능 | 티켓 탐색 | 계정 컨텍스트 조회 | FR-DASH-TCK-003 | 운영자는 티켓과 연결된 커뮤니티 사용자 및 게임 계정 요약을 확인할 수 있어야 한다. | `community_users`, `game_accounts` 조인. 민감정보는 권한별 제한 표시 |
| 기능 | 티켓 탐색 | 업무 로그 컨텍스트 조회 | FR-DASH-TCK-004 | 운영자는 결제/환불/미지급/가챠 문의의 근거 로그를 확인할 수 있어야 한다. | `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`를 `account_id`와 `payment_id` 기준으로 연결 |
| 기능 | 검수 큐 | 운영자 검토 대상 표시 | FR-DASH-REV-001 | 운영자는 `human_review`, `urgent_alert`, 검증 미달 티켓을 별도 후보로 확인할 수 있어야 한다. | `qa_ticket.status`, `ticket_analysis.routing_target`, `safety_results.safety_action` 기준 |
| 기능 | 검수 큐 | 긴급 문의 우선순위 | FR-DASH-REV-002 | 시스템은 HIGH 위험 문의와 장애성 문의를 검토 큐 상단에 표시해야 한다. | `risk_level`, `pattern_risk_level`, `routing_target` 기준 정렬 |
| 기능 | 검수 큐 | 후속 조치 맥락 제공 | FR-DASH-REV-003 | 운영자는 답변 수정, 수동 지급, 환불 처리, 긴급 대응에 필요한 근거를 확인할 수 있어야 한다. | 실제 조치 기록은 operation 워크플로우 또는 기존 로그 테이블과 연계한다. |
| 기능 | 인사이트 | 반복 문의 분석 표시 | FR-DASH-INS-001 | 운영자는 동일 사용자 또는 동일 계정의 반복 문의 후보를 확인할 수 있어야 한다. | `user_id`, `account_id`, `category`, 유사 문의 요약 기준 |
| 기능 | 인사이트 | VOC 현황 표시 | FR-DASH-INS-002 | 운영자는 고객의 소리 유형, 감성, 주요 키워드를 확인할 수 있어야 한다. | `voc_feedback.voc_type`, `sentiment`, `topic_keywords` 기준 |
| 기능 | 인사이트 | 운영 인사이트 표시 | FR-DASH-INS-003 | 운영자는 반복 이슈와 패턴 위험도 기반 운영 인사이트를 확인할 수 있어야 한다. | `insight.content_summary`, `category`, `pattern_risk_level` 표시 |
| 기능 | Observability | 처리 실패 조회 | FR-DASH-OBS-001 | 시스템 관리자는 DB 조회 실패와 처리 실패 이력을 확인할 수 있어야 한다. | `failed_queries`, `admin_event_logs` 기준 |
| 기능 | Observability | 알림 실패 조회 | FR-DASH-OBS-002 | 시스템 관리자는 Slack/Discord 등 알림 실패 원인을 확인할 수 있어야 한다. | `notification_logs.status`, `error_category`, `error_message` 기준 |
| 기능 | Observability | API Health 조회 | FR-DASH-OBS-003 | 시스템은 대시보드 API 상태를 확인할 수 있는 Health endpoint를 제공해야 한다. | `GET /health` |
| 기능 | API | 요약 API 제공 | FR-DASH-API-001 | 시스템은 운영 현황, 리스크, 응답 품질 요약 API를 제공해야 한다. | `/summary/overview`, `/summary/risk`, `/summary/quality`, `/summary/all` |
| 기능 | API | 티켓 API 제공 | FR-DASH-API-002 | 시스템은 티켓 목록과 상세 조회 API를 제공해야 한다. | `/tickets`, `/tickets/{ticket_id}` |
| 기능 | API | Streamlit 렌더링 친화 응답 | FR-DASH-API-003 | API는 Streamlit에서 바로 렌더링 가능한 숫자, 비율, 분포 배열, 목록 데이터를 반환해야 한다. | 날짜, 비율, 점수 포맷은 프론트엔드에서 일관되게 처리한다. |

## 8. 비기능 요구사항

| 분류 | 대분류 | 중분류 | 요구사항 ID | 설명 | 추가 설명 |
| --- | --- | --- | --- | --- | --- |
| 비기능 | 성능 | 요약 조회 성능 | NFR-DASH-PERF-001 | 시스템은 주요 요약 지표를 운영자가 대기 없이 확인할 수 있도록 조회 성능을 관리해야 한다. | 기본 30일 조회 기준 3초 이내 응답을 목표로 한다. |
| 비기능 | 성능 | 상세 조회 성능 | NFR-DASH-PERF-002 | 시스템은 티켓 상세 화면에서 과도한 조인 지연이 발생하지 않도록 해야 한다. | 티켓 단위 최신 레코드 조회는 `LEFT JOIN LATERAL` 또는 별도 단계 조회를 사용한다. |
| 비기능 | 성능 | 대량 목록 제한 | NFR-DASH-PERF-003 | 시스템은 목록 조회 시 제한값을 적용해 DB 부하를 방지해야 한다. | `limit` 기본 50, 최대 200 |
| 비기능 | 가용성 | API 장애 표시 | NFR-DASH-AVL-001 | 프론트엔드는 대시보드 API 장애 시 명확한 오류 메시지를 표시해야 한다. | 빈 화면 대신 API URL, endpoint, 오류 내용을 표시한다. |
| 비기능 | 가용성 | 데이터 없음 처리 | NFR-DASH-AVL-002 | 시스템은 조회 결과가 없는 경우에도 화면 구조가 깨지지 않아야 한다. | KPI는 `-`, 차트/테이블은 빈 상태 문구를 표시한다. |
| 비기능 | 가용성 | 부분 데이터 허용 | NFR-DASH-AVL-003 | 일부 테이블에 데이터가 없어도 전체 대시보드가 실패하지 않아야 한다. | `final_response`, `notification_logs`, `admin_event_logs`가 비어 있어도 요약 조회 가능 |
| 비기능 | 보안 | 접근 통제 | NFR-DASH-SEC-001 | 시스템은 대시보드 접근을 인증된 운영 인력으로 제한해야 한다. | 인증/인가 체계는 배포 환경의 운영 정책을 따른다. |
| 비기능 | 보안 | 민감정보 보호 | NFR-DASH-SEC-002 | 시스템은 계정, 결제, 환불, 문의 원문 등 민감정보 노출을 최소화해야 한다. | 역할별 마스킹과 상세 권한 분리를 적용한다. |
| 비기능 | 보안 | SQL 입력 통제 | NFR-DASH-SEC-003 | 시스템은 사용자 입력값을 SQL에 직접 연결하지 않아야 한다. | 기간, 상태, limit, ticket_id는 검증 후 파라미터 바인딩한다. |
| 비기능 | 개인정보 | 원문 표시 제한 | NFR-DASH-PRV-001 | 시스템은 `qa_ticket.raw_query`를 필요한 화면과 권한에서만 표시해야 한다. | 목록에서는 제목/요약 중심, 상세에서만 제한 표시 |
| 비기능 | 개인정보 | 로그 개인정보 최소화 | NFR-DASH-PRV-002 | 시스템은 대시보드 오류 로그에 불필요한 개인정보를 남기지 않아야 한다. | ticket_id 중심으로 추적하고 원문/결제 식별자 저장을 피한다. |
| 비기능 | 신뢰성 | 지표 산식 일관성 | NFR-DASH-REL-001 | 시스템은 대시보드 지표 산식을 `docs/dashboard/metrics.md`와 일치시켜야 한다. | PRD와 구현 문서 간 계산식 차이를 방지한다. |
| 비기능 | 신뢰성 | 최신 레코드 선택 일관성 | NFR-DASH-REL-002 | 시스템은 최신 분석, 최신 초안, 최신 안전성 결과, 최신 최종 응답 선택 규칙을 일관되게 적용해야 한다. | timestamp와 PK 내림차순 기준 |
| 비기능 | 데이터 정합성 | 실제 테이블명 준수 | NFR-DASH-DQ-001 | 시스템 문서와 구현은 실제 DB 테이블명과 컬럼명을 사용해야 한다. | `QA_ticket`이 아니라 `qa_ticket`, `raw_content`가 아니라 `raw_query`를 사용한다. |
| 비기능 | 데이터 정합성 | 상태값 의미 분리 | NFR-DASH-DQ-002 | 시스템은 티켓 상태, 라우팅 대상, 안전성 액션을 서로 다른 의미로 표시해야 한다. | `qa_ticket.status`, `ticket_analysis.routing_target`, `safety_results.safety_action` 분리 |
| 비기능 | 데이터 정합성 | 조인 기준 준수 | NFR-DASH-DQ-003 | 시스템은 DB 관계 문서에 정의된 키 기준으로 조인해야 한다. | `ticket_id`, `draft_id`, `analysis_id`, `account_id`, `payment_id` 기준 |
| 비기능 | 관측성 | API 호출 실패 추적 | NFR-DASH-OBS-001 | 시스템은 대시보드 API 호출 실패와 DB 조회 실패를 운영자가 확인할 수 있게 해야 한다. | `failed_queries`, `admin_event_logs` 또는 애플리케이션 로그와 연계 |
| 비기능 | 관측성 | 알림 이력 추적 | NFR-DASH-OBS-002 | 시스템은 알림 발송 성공/실패를 대시보드에서 추적할 수 있어야 한다. | `notification_logs` 기준 |
| 비기능 | 사용성 | 업무용 화면 밀도 | NFR-DASH-UX-001 | 대시보드는 운영자가 반복적으로 사용하는 업무 도구로서 KPI, 차트, 표를 밀도 있게 배치해야 한다. | 마케팅형 랜딩 화면이 아니라 모니터링과 탐색 중심 |
| 비기능 | 사용성 | 위험도 가독성 | NFR-DASH-UX-002 | 시스템은 위험도를 색상과 텍스트로 함께 표시해야 한다. | `critical`, `high`, `medium`, `low` 원본 값 유지 |
| 비기능 | 사용성 | 반응형 표시 | NFR-DASH-UX-003 | 시스템은 데스크톱과 좁은 화면에서 KPI와 표가 겹치지 않도록 표시해야 한다. | Streamlit wide layout과 자연스러운 컬럼 줄바꿈 허용 |
| 비기능 | 유지보수성 | 문서 체계 유지 | NFR-DASH-MNT-001 | Dashboard 요구사항 ID는 `FR-DASH-*`, `NFR-DASH-*` 형식을 따라야 한다. | 챗봇 `FR-CBOT-*`, 운영배치 `FR-BATCH-*`와 구분한다. |
| 비기능 | 유지보수성 | 모듈 단위 관리 | NFR-DASH-MNT-002 | 시스템은 API, workflow, visualization, frontend를 분리해 유지보수해야 한다. | `docs/dashboard/architecture.md`의 런타임 구성을 따른다. |
| 비기능 | 유지보수성 | 신규 지표 확장성 | NFR-DASH-MNT-003 | 시스템은 신규 운영 지표가 추가되어도 기존 화면과 API를 크게 변경하지 않고 확장할 수 있어야 한다. | summary 응답에 신규 섹션을 추가 가능한 구조 유지 |

## 9. 화면 요구사항 요약

| 화면 | 핵심 데이터 | 완료 기준 |
| --- | --- | --- |
| 홈/운영 요약 | `ticket_counts`, `response_metrics`, `source_distribution`, `status_distribution`, `routing_distribution`, `recent_tickets` | KPI 8개 이상, 주요 분포 차트, 최근 문의 목록 표시 |
| 운영 현황 | 문의량, 상태, 채널, 라우팅, 평균 응답 지연 | 조회 기간 변경 시 모든 지표가 갱신 |
| 리스크 분석 | 위험도, 감성, Safety 평균, 고위험 후보 | threshold 경고와 고위험 후보 테이블 표시 |
| 응답 품질 | 초안, 근거, 안전성, 최종 응답, 알림 상태 | 커버리지 지표와 품질 점검 후보 표시 |
| 티켓 상세 | 티켓, 계정, 분석, 초안, 근거, 안전성, 최종 응답, 알림, VOC | `ticket_id` 하나로 처리 맥락 확인 가능 |

## 10. API 요구사항 요약

| Endpoint | 목적 | 주요 요구사항 |
| --- | --- | --- |
| `GET /health` | API 상태 확인 | 대시보드 프론트엔드가 API 연결 여부를 확인할 수 있어야 한다. |
| `GET /summary/overview` | 운영 현황 요약 | 기간 필터 기반 KPI, 분포, 최근 문의 목록 반환 |
| `GET /summary/risk` | 리스크 요약 | 위험도, 감성, Safety 점수, 고위험 후보 반환 |
| `GET /summary/quality` | 응답 품질 요약 | 초안, 근거, 최종 응답, 알림, 품질 후보 반환 |
| `GET /summary/all` | 전체 요약 | 홈 화면 또는 통합 조회에 필요한 전체 요약 반환 |
| `GET /tickets` | 티켓 목록 | `limit`, `status` 필터 지원, 최신 분석/응답 메타 포함 |
| `GET /tickets/{ticket_id}` | 티켓 상세 | 티켓 처리 맥락 전체 반환 |

## 11. 완료 기준

- `docs/chatbot/prd.md`의 챗봇 대시보드 연계 요구사항과 `docs/operation/prd.md`의 운영 대시보드 요구사항을 모두 추적할 수 있다.
- 대시보드 PRD의 테이블명과 컬럼명은 `docs/DB/descriptions.md`의 실제 PostgreSQL 스키마와 충돌하지 않는다.
- `docs/dashboard/architecture.md`, `api_spec.md`, `metrics.md`, `screen_design.md`와 상충되는 신규 구조를 만들지 않는다.
- 운영자는 한 화면에서 문의 처리 현황, 위험 징후, 응답 품질, 검토 후보를 파악할 수 있다.
- 티켓 상세 화면에서 운영자가 후속 검수에 필요한 근거를 확인할 수 있다.
