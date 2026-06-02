- 운영배치 봇 기능 요구사항
    
    
    | **분류** | **요구사항명** |  |  |  | **추가설명** |
    | --- | --- | --- | --- | --- | --- |
    |  | **대분류** | **중분류** | **요구사항 ID** | **소분류(기능설명)** |  |
    | 기능 | 운영배치 Data Layer | 문의 데이터 수집 | FR-BATCH-DATA-001 | 시스템은 커뮤니티 게시글과 챗봇 문의를 수집할 수 있어야 한다 | title, raw_content, source_type, user_id, account_id를 수집한다 |
    | 기능 | 운영배치 Data Layer | 문의 원문 저장 | FR-BATCH-DATA-002 | 시스템은 수집된 문의 원문을 QA_ticket에 저장해야 한다 | ticket_id, title, raw_content, source_type, responder_type, status, inquiry_created_at 저장 |
    | 기능 | 운영배치 Data Layer | 문의 출처 구분 | FR-BATCH-DATA-003 | 시스템은 문의 유입 출처를 구분할 수 있어야 한다 | source_type을 community, chatbot 등으로 관리한다 |
    | 기능 | 운영배치 Data Layer | 문의 상태 관리 | FR-BATCH-DATA-004 | 시스템은 문의 처리 상태를 관리할 수 있어야 한다 | QA_ticket.status를 pending, analyzed, drafted, approved, human_review, closed 등으로 관리 |
    | 기능 | 운영배치 Data Layer | Vector DB 검색 준비 | FR-BATCH-DATA-005 | 시스템은 답변 생성을 위해 FAQ, 공지, 정책 문서 검색 데이터를 준비해야 한다 | documents, documents_chunks, documents_embeddings 기반 검색 준비 |
    |  |  |  |  |  |  |
    | 기능 | 계정 식별 및 조회 | 커뮤니티 계정 식별 | FR-BATCH-ACC-001 | 시스템은 QA_ticket.user_id를 기준으로 커뮤니티 계정을 식별할 수 있어야 한다 | community_users.user_id와 연계해 email, nickname, user_status 조회 |
    | 기능 | 계정 식별 및 조회 | 게임 계정 식별 | FR-BATCH-ACC-002 | 시스템은 QA_ticket.account_id를 기준으로 게임 계정을 식별할 수 있어야 한다 | game_accounts.account_id와 연계해 uid, server_region, progression_level 조회 |
    | 기능 | 계정 식별 및 조회 | 계정 상태 확인 | FR-BATCH-ACC-003 | 시스템은 문의 대상 게임 계정의 상태를 확인할 수 있어야 한다 | account_status, user_status 기준 정상/정지/제한 계정 여부 확인 |
    | 기능 | 계정 식별 및 조회 | 계정 연결성 확인 | FR-BATCH-ACC-004 | 시스템은 커뮤니티 계정과 게임 계정의 연결 관계를 확인할 수 있어야 한다 | community_users.user_id와 game_accounts.user_id 조인 기반 확인 |
    |  |  |  |  |  |  |
    | 기능 | 게임 운영 로그 조회 | 결제 로그 조회 | FR-BATCH-GLOG-001 | 시스템은 account_id 기준 결제 로그를 조회할 수 있어야 한다 | payments에서 payment_status, transaction_id, paid_at 확인 |
    | 기능 | 게임 운영 로그 조회 | 환불 로그 조회 | FR-BATCH-GLOG-002 | 시스템은 payment_id 기준 환불 로그를 조회할 수 있어야 한다 | refunds에서 refund_status, refund_reason 확인 |
    | 기능 | 게임 운영 로그 조회 | 아이템 지급 로그 조회 | FR-BATCH-GLOG-003 | 시스템은 account_id 또는 payment_id 기준 아이템 지급 로그를 조회할 수 있어야 한다 | item_delivery_logs에서 item_name, delivery_status, delivered_at 확인 |
    | 기능 | 게임 운영 로그 조회 | 가챠 로그 조회 | FR-BATCH-GLOG-004 | 시스템은 account_id 기준 가챠 이용 로그를 조회할 수 있어야 한다 | gacha_logs에서 banner_name, item_name, rarity, pity_count 확인 |
    | 기능 | 게임 운영 로그 조회 | 미지급 여부 판단 | FR-BATCH-GLOG-005 | 시스템은 결제 성공 대비 아이템 지급 실패 여부를 판단할 수 있어야 한다 | payment_status=success 및 delivery_status=fail 조합 탐지 |
    |  |  |  |  |  |  |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | Query Routing | FR-BATCH-ANA-001 | 시스템은 문의 내용을 기반으로 문의 유형을 1차 분기할 수 있어야 한다 | 결제, 환불, 미지급, 가챠, 확률, 운영 정책, 욕설, 장애 감지 유형으로 분기 |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | 문의 유형별 데이터 조회 | FR-BATCH-ANA-002 | 시스템은 분기된 문의 유형에 따라 필요한 DB를 조회할 수 있어야 한다 | 결제/미지급 문의는 account_id 기준 payments, refunds, item_delivery_logs 조회 |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | LLM 분석 수행 | FR-BATCH-ANA-003 | 시스템은 문의 원문과 조회 로그를 기반으로 LLM 분석을 수행할 수 있어야 한다 | category, risk_level, sentiment, routing_target, summary 생성 |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | 분석 결과 저장 | FR-BATCH-ANA-004 | 시스템은 문의 분석 결과를 ticket_analysis에 저장해야 한다 | analysis_id, ticket_id, category, risk_level, sentiment, routing_target, summary 저장 |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | 긴급 문의 분류 | FR-BATCH-ANA-005 | 시스템은 HIGH 위험 문의를 urgent_alert 또는 human_review 대상으로 분류할 수 있어야 한다 | risk_level과 routing_target 기준 운영자 우선 검토 대상으로 지정 |
    | 기능 | STEP1 문의 유형 및 리스크 분석 | 문의 요약 생성 | FR-BATCH-ANA-006 | 시스템은 운영자 검토용 문의 요약을 생성할 수 있어야 한다 | 결제 완료 대비 지급 로그 누락 가능성 등 핵심 원인 요약 |
    |  |  |  |  |  |  |
    | 기능 | STEP2 RAG 검색 | Hybrid Retriever 실행 | FR-BATCH-RAG-001 | 시스템은 RAG 답변이 필요한 문의에 대해 Hybrid Retriever를 실행해야 한다 | BM25와 Vector Search를 결합해 관련 문서 검색 |
    | 기능 | STEP2 RAG 검색 | Vector DB 유사도 검색 | FR-BATCH-RAG-002 | 시스템은 documents_embeddings를 기준으로 유사 문서를 검색할 수 있어야 한다 | embedding similarity search 수행 |
    | 기능 | STEP2 RAG 검색 | 관련 Chunk 조회 | FR-BATCH-RAG-003 | 시스템은 검색된 embedding 결과를 기준으로 documents_chunks를 조회할 수 있어야 한다 | chunk_id 기준 chunk_text, token_count 조회 |
    | 기능 | STEP2 RAG 검색 | 문서 원문 조회 | FR-BATCH-RAG-004 | 시스템은 chunk의 원문 문서를 추적할 수 있어야 한다 | document_id 기준 FAQ, 공지, 정책 원문 조회 |
    | 기능 | STEP2 RAG 검색 | 검색 점수 저장 | FR-BATCH-RAG-005 | 시스템은 검색된 근거 문서의 relevance_score를 저장할 수 있어야 한다 | evidence_docs 또는 검색 로그에 score 저장 |
    |  |  |  |  |  |  |
    | 기능 | STEP2 답변 초안 생성 | 라우팅 결과 확인 | FR-BATCH-RES-001 | 시스템은 ticket_analysis.routing_target을 기준으로 답변 생성 경로를 결정해야 한다 | rag_reply, urgent_alert, human_review 등 분기 |
    | 기능 | STEP2 답변 초안 생성 | 답변 초안 생성 | FR-BATCH-RES-002 | 시스템은 분석 결과와 검색 근거를 기반으로 답변 초안을 생성해야 한다 | answer_draft에 draft_text 생성 |
    | 기능 | STEP2 답변 초안 생성 | 프롬프트 버전 저장 | FR-BATCH-RES-003 | 시스템은 답변 생성에 사용된 프롬프트 버전을 저장해야 한다 | answer_draft.prompt_version 저장 |
    | 기능 | STEP2 답변 초안 생성 | 근거 문서 저장 | FR-BATCH-RES-004 | 시스템은 답변 생성에 사용된 근거 문서를 evidence_docs에 저장해야 한다 | source_type, source_id, evidence_text, relevance_score 저장 |
    | 기능 | STEP2 답변 초안 생성 | 긴급 문의 초안 생성 | FR-BATCH-RES-005 | 시스템은 urgent_alert 문의에 대해 운영자 검토용 초안을 생성할 수 있어야 한다 | 자동 게시가 아닌 운영자 검수 전제의 안내 초안 생성 |
    |  |  |  |  |  |  |
    | 기능 | Approval Gate | 답변 안전성 검사 | FR-BATCH-APP-001 | 시스템은 생성된 답변 초안의 안전성을 검사해야 한다 | answer_draft와 evidence_docs를 기반으로 검증 |
    | 기능 | Approval Gate | 근거 문서 일치 검사 | FR-BATCH-APP-002 | 시스템은 답변 내용과 근거 문서의 일치 여부를 검사할 수 있어야 한다 | 근거 불일치 시 human_review로 분기 |
    | 기능 | Approval Gate | Hallucination 검사 | FR-BATCH-APP-003 | 시스템은 생성 답변의 Hallucination 가능성을 검사할 수 있어야 한다 | hallucination_score 산출 |
    | 기능 | Approval Gate | 정책 위반 검사 | FR-BATCH-APP-004 | 시스템은 생성 답변의 운영 정책 위반 여부를 검사할 수 있어야 한다 | policy_violation_score 산출 |
    | 기능 | Approval Gate | 유해 표현 검사 | FR-BATCH-APP-005 | 시스템은 생성 답변의 욕설 및 유해 표현 포함 여부를 검사할 수 있어야 한다 | toxicity_score 산출 |
    | 기능 | Approval Gate | Safety 결과 저장 | FR-BATCH-APP-006 | 시스템은 안전성 검증 결과를 safety_results에 저장해야 한다 | hallucination_score, toxicity_score, policy_violation_score, factuality_score 저장 |
    | 기능 | Approval Gate | 승인 결과 분기 | FR-BATCH-APP-007 | 시스템은 safety_results를 기준으로 approved, human_review, urgent_alert로 분기해야 한다 | 통과 시 최종 응답, 미달 또는 긴급 시 운영자 검수 |
    |  |  |  |  |  |  |
    | 기능 | Human-in-the-loop | 운영자 검수 | FR-BATCH-HITL-001 | 운영자는 human_review 또는 urgent_alert 문의를 검수할 수 있어야 한다 | 답변 초안, 근거 문서, 안전성 결과 확인 |
    | 기능 | Human-in-the-loop | 답변 수정 | FR-BATCH-HITL-002 | 운영자는 생성된 답변 초안을 수정할 수 있어야 한다 | 수정 전후 답변과 수정 사유 저장 가능 |
    | 기능 | Human-in-the-loop | 수동 지급 처리 | FR-BATCH-HITL-003 | 운영자는 미지급 문의에 대해 수동 지급 처리 결과를 기록할 수 있어야 한다 | account_id, item_name, action_type, action_at 기록 |
    | 기능 | Human-in-the-loop | 환불 처리 기록 | FR-BATCH-HITL-004 | 운영자는 환불 관련 처리 결과를 기록할 수 있어야 한다 | payment_id, refund_status, refund_reason, admin_id 기록 |
    | 기능 | Human-in-the-loop | 긴급 대응 기록 | FR-BATCH-HITL-005 | 운영자는 긴급 문의에 대한 대응 내용을 기록할 수 있어야 한다 | 장애성 문의, HIGH 위험 문의, 반복 이슈 대응 이력 저장 |
    | 기능 | Human-in-the-loop | 최종 응답 게시 | FR-BATCH-HITL-006 | 시스템은 운영자 검수 완료 후 최종 응답을 게시할 수 있어야 한다 | 커뮤니티 답변 게시 또는 챗봇 응답 전달 |
    | 기능 | Human-in-the-loop | 티켓 종료 처리 | FR-BATCH-HITL-007 | 시스템은 최종 응답 게시 후 QA_ticket.status를 closed로 변경해야 한다 | 최종 처리 완료 상태 반영 |
    |  |  |  |  |  |  |
    | 기능 | STEP3 운영 인사이트 | 운영 통계 집계 | FR-BATCH-INS-001 | 시스템은 분석 결과, 안전성 결과, 최종 응답 결과를 집계할 수 있어야 한다 | ticket_analysis, safety_results, 최종 응답 결과 기반 집계 |
    | 기능 | STEP3 운영 인사이트 | 반복 문의 분석 | FR-BATCH-INS-002 | 시스템은 동일 문의 반복 여부를 분석할 수 있어야 한다 | user_id, account_id, category, 키워드 기준 반복 문의 탐지 |
    | 기능 | STEP3 운영 인사이트 | 감성 변화 분석 | FR-BATCH-INS-003 | 시스템은 문의 감성 변화 추이를 분석할 수 있어야 한다 | sentiment 기준 negative 증가 여부 확인 |
    | 기능 | STEP3 운영 인사이트 | 위험 키워드 증가율 분석 | FR-BATCH-INS-004 | 시스템은 위험 키워드 증가율을 분석할 수 있어야 한다 | 결제 미지급, 서버 장애, 로그인 오류 등 키워드 증가율 계산 |
    | 기능 | STEP3 운영 인사이트 | 인사이트 저장 | FR-BATCH-INS-005 | 시스템은 운영 인사이트 결과를 insight에 저장해야 한다 | insight_id, user_id, ticket_id, account_id, content_summary, category, sentiment, risk_level 저장 |
    | 기능 | STEP3 운영 인사이트 | 패턴 위험도 산출 | FR-BATCH-INS-006 | 시스템은 반복 이슈의 패턴 위험도를 산출할 수 있어야 한다 | pattern_risk_level 기준 운영 위험도 분류 |
    |  |  |  |  |  |  |
    | 기능 | Observability Layer | 결제 미지급 증가율 모니터링 | FR-BATCH-OBS-001 | 시스템은 결제 미지급 문의 증가율을 모니터링할 수 있어야 한다 | payment_success 대비 delivery_fail 증가율 추적 |
    | 기능 | Observability Layer | HIGH 위험 문의 수 모니터링 | FR-BATCH-OBS-002 | 시스템은 HIGH 위험 문의 수를 모니터링할 수 있어야 한다 | risk_level=HIGH 문의 수 집계 |
    | 기능 | Observability Layer | 재문의율 모니터링 | FR-BATCH-OBS-003 | 시스템은 동일 사용자 또는 동일 계정의 재문의율을 모니터링할 수 있어야 한다 | user_id/account_id 기준 반복 문의 비율 산출 |
    | 기능 | Observability Layer | 운영자 수정 비율 모니터링 | FR-BATCH-OBS-004 | 시스템은 운영자가 답변 초안을 수정한 비율을 모니터링할 수 있어야 한다 | draft_text와 final_text 비교 기반 수정률 계산 |
    | 기능 | Observability Layer | 답변 승인율 모니터링 | FR-BATCH-OBS-005 | 시스템은 생성 답변의 승인율을 모니터링할 수 있어야 한다 | approved, human_review, rejected 비율 제공 |
    | 기능 | Observability Layer | 운영 알림 발송 | FR-BATCH-OBS-006 | 시스템은 위험 문의 또는 장애성 문의 급증 시 Slack/Discord 알림을 발송할 수 있어야 한다 | alert_type, target_channel, sent_at 저장 |
    | 기능 | Observability Layer | 운영 대시보드 제공 | FR-BATCH-OBS-007 | 시스템은 운영자가 배치 처리 현황과 주요 지표를 확인할 수 있는 대시보드를 제공해야 한다 | 처리 건수, 실패 건수, 승인율, 위험 문의 수, 재문의율 표시 |
    |  |  |  |  |  |  |
    |  |  |  |  |  |  |
    |  |  |  |  |  |  |



    | 비기능 | 운영배치 성능 | 배치 처리 시간 | NFR-BATCH-PERF-001 | 시스템은 정해진 배치 시간 내 문의 수집, 분석, 답변 초안 생성, 안전성 검증을 완료해야 한다 | STEP1, STEP2, Approval Gate, STEP3 단계별 처리 시간을 측정한다 |
| --- | --- | --- | --- | --- | --- |
| 비기능 | 운영배치 성능 | 문의 수집 처리량 | NFR-BATCH-PERF-002 | 시스템은 커뮤니티 게시글과 챗봇 문의가 증가해도 수집 지연을 최소화해야 한다 | 일 단위 문의량 증가에 대응할 수 있도록 Queue 또는 Worker 기반 처리 구조를 고려한다 |
| 비기능 | 운영배치 성능 | DB 조회 성능 | NFR-BATCH-PERF-003 | 시스템은 account_id 기준 결제·환불·아이템 지급·가챠 로그 조회를 일정 시간 이내 수행해야 한다 | payments, refunds, item_delivery_logs, gacha_logs 조회 성능을 관리한다 |
| 비기능 | 운영배치 성능 | RAG 검색 성능 | NFR-BATCH-PERF-004 | 시스템은 Hybrid Retriever와 Vector DB 검색 지연 시간을 관리해야 한다 | BM25, Vector Search, documents_chunks 조회 시간을 로그로 기록한다 |
| 비기능 | 운영배치 성능 | LLM 호출 성능 | NFR-BATCH-PERF-005 | 시스템은 LLM 분석 및 답변 생성 지연 시간을 추적해야 한다 | model_name, latency, token_count를 저장하고 임계치 초과 시 알림 처리한다 |
| 비기능 | 운영배치 성능 | 대시보드 조회 성능 | NFR-BATCH-PERF-006 | 시스템은 운영자가 주요 지표를 조회할 때 과도한 지연이 발생하지 않도록 해야 한다 | 처리 건수, 승인율, 위험 문의 수, 재문의율 조회 성능을 관리한다 |
|  |  |  |  |  |  |
| 비기능 | 운영배치 가용성 | 배치 실행 안정성 | NFR-BATCH-AVL-001 | 시스템은 정기 운영 배치가 중단되지 않도록 안정적으로 실행되어야 한다 | 실패 시 재시도 또는 미처리 티켓 보존이 가능해야 한다 |
| 비기능 | 운영배치 가용성 | 부분 장애 대응 | NFR-BATCH-AVL-002 | 시스템은 일부 DB 또는 외부 서비스 장애가 전체 배치 중단으로 이어지지 않도록 해야 한다 | Vector DB, LLM API, Slack/Discord 장애를 단계별로 격리한다 |
| 비기능 | 운영배치 가용성 | 미처리 티켓 복구 | NFR-BATCH-AVL-003 | 시스템은 배치 실패 후 미처리 티켓을 재처리할 수 있어야 한다 | QA_ticket.status 기준 pending, analyzed, drafted 상태를 재처리 대상으로 식별한다 |
| 비기능 | 운영배치 가용성 | 수동 처리 전환 | NFR-BATCH-AVL-004 | 시스템은 자동 분석 또는 답변 생성 실패 시 운영자 검수로 전환할 수 있어야 한다 | human_review 상태로 변경하고 실패 사유를 저장한다 |
| 비기능 | 운영배치 가용성 | 알림 채널 장애 대응 | NFR-BATCH-AVL-005 | 시스템은 Slack/Discord 알림 실패 시 실패 이력을 저장해야 한다 | alert_type, target_channel, sent_at, failure_reason을 저장한다 |
| 비기능 | 운영배치 가용성 | 중복 실행 방지 | NFR-BATCH-AVL-006 | 시스템은 동일 배치 작업이 중복 실행되어 동일 문의가 중복 처리되지 않도록 해야 한다 | batch_job_id, ticket_id, status 기준 중복 실행을 방지한다 |
|  |  |  |  |  |  |
| 비기능 | 운영배치 확장성 | 문의량 확장 대응 | NFR-BATCH-SCL-001 | 시스템은 문의량 증가에 따라 배치 처리 용량을 확장할 수 있어야 한다 | 수집 파이프라인, 분석 Worker, 답변 생성 Worker의 수평 확장을 고려한다 |
| 비기능 | 운영배치 확장성 | 신규 문의 유형 확장 | NFR-BATCH-SCL-002 | 시스템은 신규 문의 유형이 추가되어도 Query Routing 구조를 확장할 수 있어야 한다 | 결제, 환불, 미지급, 가챠, 정책, 장애 외 신규 category 추가가 가능해야 한다 |
| 비기능 | 운영배치 확장성 | 지식베이스 확장 | NFR-BATCH-SCL-003 | 시스템은 FAQ, 공지, 정책 문서 증가에도 검색 성능을 유지해야 한다 | documents, documents_chunks, documents_embeddings 증가에 대응한다 |
| 비기능 | 운영배치 확장성 | 분석 모델 교체 가능성 | NFR-BATCH-SCL-004 | 시스템은 LLM 모델 및 분석 프롬프트를 교체할 수 있어야 한다 | model_name, prompt_version 기반으로 모델 변경을 추적한다 |
| 비기능 | 운영배치 확장성 | 채널 확장성 | NFR-BATCH-SCL-005 | 시스템은 커뮤니티와 챗봇 외 신규 문의 채널을 추가할 수 있어야 한다 | source_type 확장 구조를 유지한다 |
| 비기능 | 운영배치 확장성 | 알림 채널 확장성 | NFR-BATCH-SCL-006 | 시스템은 Slack/Discord 외 추가 알림 채널을 확장할 수 있어야 한다 | alert_type, target_channel 구조를 확장 가능하게 관리한다 |
|  |  |  |  |  |  |
| 비기능 | 운영배치 보안 | 데이터 접근 통제 | NFR-BATCH-SEC-001 | 시스템은 QA_ticket, community_users, game_accounts, payments 등 민감 데이터 접근을 통제해야 한다 | 관리자, 상담원, 시스템 계정별 접근 권한을 분리한다 |
| 비기능 | 운영배치 보안 | 결제 로그 보호 | NFR-BATCH-SEC-002 | 시스템은 결제·환불 로그 조회 시 불필요한 민감 정보가 노출되지 않도록 해야 한다 | transaction_id, payment_id, refund_reason 접근 범위를 제한한다 |
| 비기능 | 운영배치 보안 | 운영자 권한 관리 | NFR-BATCH-SEC-003 | 시스템은 운영자별 권한에 따라 검수, 수정, 수동 지급, 환불 처리 권한을 분리해야 한다 | admin_id 기준 역할 기반 접근 제어를 적용한다 |
| 비기능 | 운영배치 보안 | 프롬프트 인젝션 방어 | NFR-BATCH-SEC-004 | 시스템은 문의 원문에 포함된 프롬프트 인젝션 시도를 탐지해야 한다 | 시스템 명령 노출 유도, 정책 우회 요청, 보안 규칙 무시 요청을 검사한다 |
| 비기능 | 운영배치 보안 | 외부 연동 보안 | NFR-BATCH-SEC-005 | 시스템은 LLM API, Slack, Discord, GitHub 등 외부 연동 정보를 안전하게 관리해야 한다 | API Key, Webhook URL, Token은 환경 변수 또는 Secret Manager로 관리한다 |
| 비기능 | 운영배치 보안 | 대시보드 접근 보안 | NFR-BATCH-SEC-006 | 시스템은 운영 대시보드 접근을 인증된 사용자로 제한해야 한다 | 상담원, 운영자, 관리자 권한에 따라 조회 범위를 제한한다 |
|  |  |  |  |  |  |
| 비기능 | 개인정보 및 데이터 보호 | 개인정보 최소 수집 | NFR-BATCH-PRV-001 | 시스템은 문의 처리에 필요한 최소한의 사용자 정보만 수집해야 한다 | user_id, account_id, source_type 등 처리에 필요한 항목 중심으로 수집한다 |
| 비기능 | 개인정보 및 데이터 보호 | 원문 데이터 보호 | NFR-BATCH-PRV-002 | 시스템은 QA_ticket.raw_content에 포함된 개인정보를 보호해야 한다 | 문의 원문 접근 권한 제한 및 필요 시 마스킹 처리를 적용한다 |
| 비기능 | 개인정보 및 데이터 보호 | 로그 개인정보 마스킹 | NFR-BATCH-PRV-003 | 시스템은 배치 로그와 Observability 로그에 불필요한 개인정보가 저장되지 않도록 해야 한다 | 이메일, UID, 결제 식별자 등 민감 정보는 마스킹 또는 비식별 처리한다 |
| 비기능 | 개인정보 및 데이터 보호 | 데이터 보존 기간 관리 | NFR-BATCH-PRV-004 | 시스템은 문의, 답변, 안전성 결과, 운영 로그의 보존 기간을 관리해야 한다 | 운영 정책에 따라 저장 기간과 삭제 기준을 정의한다 |
| 비기능 | 개인정보 및 데이터 보호 | 상담원 화면 노출 제한 | NFR-BATCH-PRV-005 | 시스템은 상담원 화면에서 업무 처리에 필요한 범위의 개인정보만 노출해야 한다 | 결제/계정/환불 정보는 최소 권한 기준으로 표시한다 |
|  |  |  |  |  |  |
| 비기능 | 운영배치 신뢰성 | 분석 결과 신뢰성 | NFR-BATCH-REL-001 | 시스템은 문의 유형, risk_level, sentiment, routing_target 분석 결과의 일관성을 유지해야 한다 | ticket_analysis 저장 전 필수값 및 허용값 검증을 수행한다 |
| 비기능 | 운영배치 신뢰성 | 근거 기반 답변 | NFR-BATCH-REL-002 | 시스템은 답변 초안이 근거 문서 또는 운영 로그에 기반하도록 해야 한다 | answer_draft와 evidence_docs의 연결 관계를 유지한다 |
| 비기능 | 운영배치 신뢰성 | Hallucination 방지 | NFR-BATCH-REL-003 | 시스템은 근거 없는 답변 생성 가능성을 낮춰야 한다 | hallucination_score 기준 미달 시 human_review로 분기한다 |
| 비기능 | 운영배치 신뢰성 | 정책 준수 | NFR-BATCH-REL-004 | 시스템은 생성 답변이 게임 운영 정책을 위반하지 않도록 검증해야 한다 | policy_violation_score를 산출하고 기준 초과 시 운영자 검수로 전환한다 |
| 비기능 | 운영배치 신뢰성 | 결제/지급 판단 신뢰성 | NFR-BATCH-REL-005 | 시스템은 결제 및 미지급 판단 시 실제 운영 로그를 기준으로 처리해야 한다 | payments, refunds, item_delivery_logs 조회 결과 기반으로 판단한다 |
| 비기능 | 운영배치 신뢰성 | 승인 결과 신뢰성 | NFR-BATCH-REL-006 | 시스템은 approved, human_review, urgent_alert 분기 기준을 일관되게 적용해야 한다 | safety_results와 routing_target 기준으로 승인 결과를 결정한다 |
|  |  |  |  |  |  |
| 비기능 | 데이터 정합성 | 티켓 상태 정합성 | NFR-BATCH-DQ-001 | 시스템은 QA_ticket.status가 실제 처리 단계와 일치하도록 관리해야 한다 | pending, analyzed, drafted, approved, human_review, closed 상태값을 단계별로 갱신한다 |
| 비기능 | 데이터 정합성 | 계정 연결 정합성 | NFR-BATCH-DQ-002 | 시스템은 community_users와 game_accounts의 연결 관계가 일관되도록 관리해야 한다 | user_id, account_id 조인 결과 불일치 시 예외 처리한다 |
| 비기능 | 데이터 정합성 | 운영 로그 연결 정합성 | NFR-BATCH-DQ-003 | 시스템은 payments, refunds, item_delivery_logs 간 연결 관계를 유지해야 한다 | payment_id, account_id 기준 결제/환불/지급 로그 연결 오류를 방지한다 |
| 비기능 | 데이터 정합성 | 분석 결과 정합성 | NFR-BATCH-DQ-004 | 시스템은 ticket_analysis의 category와 routing_target이 일관되도록 관리해야 한다 | category와 처리 경로 간 불일치 발생 시 검증 오류로 기록한다 |
| 비기능 | 데이터 정합성 | 답변 근거 정합성 | NFR-BATCH-DQ-005 | 시스템은 answer_draft와 evidence_docs의 연결 관계를 유지해야 한다 | draft_id, source_id, evidence_text 기준 근거 추적이 가능해야 한다 |
| 비기능 | 데이터 정합성 | 중복 문의 관리 | NFR-BATCH-DQ-006 | 시스템은 동일 사용자의 반복 또는 중복 문의를 식별할 수 있어야 한다 | user_id, account_id, category, created_at, raw_content 유사도 기준으로 판단한다 |
|  |  |  |  |  |  |
| 비기능 | 감사 및 추적성 | 배치 실행 이력 추적 | NFR-BATCH-AUD-001 | 시스템은 운영 배치 실행 이력을 추적할 수 있어야 한다 | batch_job_id, started_at, ended_at, success_count, fail_count 저장 |
| 비기능 | 감사 및 추적성 | 처리 경로 추적 | NFR-BATCH-AUD-002 | 시스템은 각 문의가 어떤 처리 경로를 거쳤는지 추적할 수 있어야 한다 | Query Routing, RAG, Approval Gate, Human-in-the-loop 경로를 기록한다 |
| 비기능 | 감사 및 추적성 | 답변 생성 근거 추적 | NFR-BATCH-AUD-003 | 시스템은 답변 생성에 사용된 근거 문서를 추적할 수 있어야 한다 | evidence_docs와 documents, documents_chunks 연결 관계를 기록한다 |
| 비기능 | 감사 및 추적성 | Safety 검증 이력 추적 | NFR-BATCH-AUD-004 | 시스템은 Safety 검증 결과와 분기 사유를 추적할 수 있어야 한다 | hallucination_score, toxicity_score, policy_violation_score, factuality_score 저장 |
| 비기능 | 감사 및 추적성 | 운영자 조치 이력 추적 | NFR-BATCH-AUD-005 | 시스템은 운영자의 수정, 반려, 수동 지급, 환불 처리 이력을 저장해야 한다 | admin_id, action_type, action_at, edited_reason 저장 |
| 비기능 | 감사 및 추적성 | 프롬프트 변경 이력 추적 | NFR-BATCH-AUD-006 | 시스템은 답변 생성 프롬프트 변경 이력을 추적할 수 있어야 한다 | prompt_version, 변경 사유, 성능 지표를 저장한다 |
|  |  |  |  |  |  |
| 비기능 | 운영성 | 운영자 검토 큐 관리 | NFR-BATCH-OPS-001 | 시스템은 human_review와 urgent_alert 문의를 별도 검토 큐로 관리해야 한다 | 운영자 우선순위 처리를 위해 risk_level, routing_target 기준 정렬을 제공한다 |
| 비기능 | 운영성 | 긴급 문의 우선 처리 | NFR-BATCH-OPS-002 | 시스템은 HIGH 위험 문의와 장애성 문의를 우선 처리 대상으로 분류해야 한다 | urgent_alert 문의는 대시보드와 알림 채널에서 별도 표시한다 |
| 비기능 | 운영성 | 운영 지표 제공 | NFR-BATCH-OPS-003 | 시스템은 배치 처리량, 실패 건수, 승인율, 운영자 수정 비율을 운영 지표로 제공해야 한다 | 일/주/월 단위 지표 집계를 제공한다 |
| 비기능 | 운영성 | 장애 알림 | NFR-BATCH-OPS-004 | 시스템은 주요 처리 단계 실패 시 운영자에게 알림을 제공해야 한다 | 수집 실패, DB 조회 실패, LLM 호출 실패, Vector DB 장애를 알림 대상으로 관리한다 |
| 비기능 | 운영성 | 수동 처리 지원 | NFR-BATCH-OPS-005 | 시스템은 자동 처리 불가 문의에 대해 운영자가 후속 조치를 수행할 수 있도록 지원해야 한다 | 답변 수정, 수동 지급, 환불 처리, 긴급 대응 기록 기능과 연계한다 |
| 비기능 | 운영성 | 운영 대시보드 가독성 | NFR-BATCH-OPS-006 | 시스템은 운영자가 주요 배치 상태를 쉽게 확인할 수 있도록 대시보드를 제공해야 한다 | 처리 상태, 위험도, 승인율, 알림 현황을 구분해 표시한다 |
|  |  |  |  |  |  |
| 비기능 | 관측성 | 요청 및 처리 로그 저장 | NFR-BATCH-OBS-001 | 시스템은 문의 입력, DB 조회, 분석 결과, 답변 생성 결과를 로그로 기록해야 한다 | Request logging과 batch processing logging을 함께 수행한다 |
| 비기능 | 관측성 | 검색 품질 추적 | NFR-BATCH-OBS-002 | 시스템은 RAG 검색 결과와 relevance_score를 추적해야 한다 | chunk_id, retriever_type, relevance_score를 저장한다 |
| 비기능 | 관측성 | 모델 호출 로그 저장 | NFR-BATCH-OBS-003 | 시스템은 LLM 호출 이력을 저장해야 한다 | model_name, prompt_version, latency, token_count 저장 |
| 비기능 | 관측성 | 응답 품질 추적 | NFR-BATCH-OBS-004 | 시스템은 생성 답변의 승인율과 운영자 수정 비율을 추적해야 한다 | approved, human_review, rejected 비율과 수정 여부를 분석한다 |
| 비기능 | 관측성 | 위험 문의 추적 | NFR-BATCH-OBS-005 | 시스템은 HIGH 위험 문의 수와 위험 키워드 증가율을 추적해야 한다 | risk_level, risk keyword, category 기준으로 집계한다 |
| 비기능 | 관측성 | 알림 이력 추적 | NFR-BATCH-OBS-006 | 시스템은 Slack/Discord 등 운영 알림 발송 이력을 저장해야 한다 | alert_type, target_channel, sent_at, status 저장 |
|  |  |  |  |  |  |
| 비기능 | 유지보수성 | 모듈 단위 변경 관리 | NFR-BATCH-MNT-002 | 시스템은 Data, Analysis, RAG, Response, Approval, HITL, Insight, Observability 단위로 변경 관리되어야 한다 | 단계별 변경 영향 범위를 추적한다 |
| 비기능 | 유지보수성 | 설정값 관리 | NFR-BATCH-MNT-003 | 시스템은 routing 기준, risk_level 기준, factuality_score 기준, alert 기준값을 관리할 수 있어야 한다 | 운영 환경별 threshold 조정이 가능해야 한다 |
| 비기능 | 유지보수성 | 프롬프트 버전 관리 | NFR-BATCH-MNT-004 | 시스템은 답변 생성 및 분석 프롬프트 버전을 관리해야 한다 | prompt_version 기준 성능 비교 및 롤백이 가능해야 한다 |
| 비기능 | 유지보수성 | 문서화 관리 | NFR-BATCH-MNT-005 | 시스템은 배치 흐름, DB 연결, 운영자 처리 기준을 문서화해야 한다 | 운영자와 개발자가 동일한 처리 기준을 확인할 수 있어야 한다 |
| 비기능 | 유지보수성 | 테스트 가능성 | NFR-BATCH-MNT-006 | 시스템은 배치 단계별 테스트가 가능해야 한다 | 수집, 분석, RAG, Approval, HITL, Insight 단위 테스트 케이스를 구성한다 |