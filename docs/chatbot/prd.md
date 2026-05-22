| 기능 | 챗봇 Access Layer | 챗봇 문의 입력 | FR-CBOT-ACS-001 | 사용자는 챗봇을 통해 게임 문의를 입력할 수 있어야 한다 | 챗봇 UI 또는 채팅 인터페이스를 통해 문의 원문 수집 |
| --- | --- | --- | --- | --- | --- |
| 기능 | 챗봇 Access Layer | 사용자 인증 연계 | FR-CBOT-ACS-002 | 시스템은 챗봇 문의자의 사용자 정보를 식별할 수 있어야 한다 | user_id, account_id 연계 기반 문의 처리 |
| 기능 | 챗봇 Access Layer | 사용자·임직원 권한 분리 | FR-CBOT-ACS-003 | 시스템은 챗봇 사용자와 상담원/운영자 권한을 분리해야 한다 | 사용자는 문의 입력, 상담원은 검토 및 수동 처리 권한 보유 |
|  |  |  |  |  |  |
| 기능 | 챗봇 입력 전처리 | 욕설 감지 | FR-CBOT-PRE-001 | 시스템은 사용자 입력 내 욕설 및 공격적 표현을 감지할 수 있어야 한다 | Toxic 필터링을 통해 부적절 표현 탐지 |
| 기능 | 챗봇 입력 전처리 | 욕설 마스킹 | FR-CBOT-PRE-002 | 시스템은 감지된 욕설을 마스킹 처리할 수 있어야 한다 | 욕설 부분을 *** 처리한 뒤 후속 분석 단계로 전달 |
| 기능 | 챗봇 입력 전처리 | 입력 원문 보존 | FR-CBOT-PRE-003 | 시스템은 사용자 원문과 전처리된 문장을 구분해 저장할 수 있어야 한다 | raw_content, cleaned_content 분리 저장 가능 |
|  |  |  |  |  |  |
| 기능 | 챗봇 문의 저장 | 챗봇 문의 티켓 생성 | FR-CBOT-TCK-001 | 시스템은 챗봇 문의를 QA_ticket에 저장해야 한다 | title, raw_content, source_type, user_id, account_id 저장 |
| 기능 | 챗봇 문의 저장 | 문의 출처 저장 | FR-CBOT-TCK-002 | 시스템은 챗봇 문의의 source_type을 chatbot으로 저장해야 한다 | 커뮤니티 문의와 구분하기 위한 source_type 관리 |
| 기능 | 챗봇 문의 저장 | 이전 문의 Context 조회 | FR-CBOT-TCK-003 | 시스템은 챗봇 응답 생성 전 사용자의 이전 문의 이력을 조회할 수 있어야 한다 | QA_ticket READ를 통해 과거 대화 및 문의 이력 확인 |
|  |  |  |  |  |  |
| 기능 | 챗봇 문의 분석 | FAQ 유사도 측정 | FR-CBOT-ANA-001 | 시스템은 사용자 문의와 FAQ 문서의 유사도를 측정할 수 있어야 한다 | Vector DB 기반 FAQ 문서 유사도 비교 |
| 기능 | 챗봇 문의 분석 | FAQ 선분기 | FR-CBOT-ANA-002 | 시스템은 FAQ 유사도가 높은 문의를 FAQ 처리 경로로 분기할 수 있어야 한다 | 유사도 기준 이상이면 FAQ 경로로 분기 |
| 기능 | 챗봇 문의 분석 | LLM 기반 문의 분류 | FR-CBOT-ANA-003 | 시스템은 FAQ 유사도가 낮은 문의를 LLM으로 분류할 수 있어야 한다 | 결제, 인게임 버그, 고객의 소리등으로 분류 |
| 기능 | 챗봇 문의 분석 | 카테고리 라우팅 | FR-CBOT-ANA-004 | 시스템은 분석된 카테고리에 따라 처리 모듈을 분기할 수 있어야 한다 | 결제 처리, 인게임 버그 처리, FAQ 처리, 고객의 소리 처리로 분기 |
| 기능 | 챗봇 문의 분석 | 분석 결과 저장 | FR-CBOT-ANA-005 | 시스템은 챗봇 문의 분석 결과를 저장해야 한다 | ticket_analysis에 category, content, routing_target 저장 |
|  |  |  |  |  |  |
| 기능 | 챗봇 결제 문의 처리 | 결제 로그 통합 조회 | FR-CBOT-PAY-001 | 시스템은 결제 문의 처리 시 결제·환불·아이템 지급 로그를 함께 조회할 수 있어야 한다 | payments, refunds, item_delivery_logs 조회 |
| 기능 | 챗봇 결제 문의 처리 | 결제 진입 경로 확인 | FR-CBOT-PAY-002 | 시스템은 결제 문의가 직접 진입했는지 미지급 버그에서 넘어왔는지 구분할 수 있어야 한다 | ticket_analysis.routing_target 기준 확인 |
| 기능 | 챗봇 결제 문의 처리 | 직접 결제 문의 처리 | FR-CBOT-PAY-003 | 시스템은 결제 문의로 직접 분류된 경우 고객 의도에 따라 처리 방향을 결정할 수 있어야 한다 | 결제 성공, 환불 요청, 중복 결제 등 의도 기반 처리 |
| 기능 | 챗봇 결제 문의 처리 | 미지급 버그 연계 처리 | FR-CBOT-PAY-004 | 시스템은 미지급 버그에서 넘어온 결제 문의를 환불 또는 아이템 지급 방향으로 판단할 수 있어야 한다 | 기존 ticket_id를 유지하고 결제 처리 흐름으로 연결 |
| 기능 | 챗봇 결제 문의 처리 | 결제 관련 문서 검색 | FR-CBOT-PAY-005 | 시스템은 결제 문의 처리 시 관련 FAQ/정책 문서를 검색하고 재정렬할 수 있어야 한다 | Embed → Vector DB Search → Rerank 수행 |
| 기능 | 챗봇 결제 문의 처리 | 결제 답변 초안 생성 | FR-CBOT-PAY-006 | 시스템은 결제 문의에 대한 답변 초안과 근거 문서를 생성·저장해야 한다 | answer_draft WRITE, evidence_docs WRITE 수행 |
| 기능 | 챗봇 결제 문의 처리 | 결제 문의 상담원 전달 | FR-CBOT-PAY-007 | 시스템은 결제 확인이 필요한 문의를 상담원에게 context와 함께 전달할 수 있어야 한다 | 담당자 확인 후 안내 메시지 및 처리 context 전달 |
|  |  |  |  |  |  |
| 기능 | 챗봇 인게임 버그 처리 | 버그 관련 로그 조회 | FR-CBOT-BUG-001 | 시스템은 인게임 버그 문의 처리 시 가챠 로그와 아이템 지급 로그를 조회할 수 있어야 한다 | gacha_logs, item_delivery_logs 기준 실제 지급 여부 확인 |
| 기능 | 챗봇 인게임 버그 처리 | 버그 유형 판단 | FR-CBOT-BUG-002 | 시스템은 인게임 버그를 자체 버그와 미지급 버그로 구분할 수 있어야 한다 | 버그 유형에 따라 처리 경로 분리 |
| 기능 | 챗봇 인게임 버그 처리 | 자체 버그 고정 응대 | FR-CBOT-BUG-003 | 시스템은 자체 버그 문의에 대해 접수 안내 메시지를 생성할 수 있어야 한다 | 확인 후 안내드리겠습니다 등의 고정 응대 메시지 생성 |
| 기능 | 챗봇 인게임 버그 처리 | GitHub 이슈 자동 생성 | FR-CBOT-BUG-004 | 시스템은 자체 버그로 판단된 문의를 개발팀 전달용 GitHub 이슈로 생성할 수 있어야 한다 | 문의 원문, 로그 조회 결과, 사용자 환경 정보 포함 가능 |
| 기능 | 챗봇 인게임 버그 처리 | 미지급 버그 결제 연계 | FR-CBOT-BUG-005 | 시스템은 미지급 버그를 결제 문의 처리 흐름으로 연결할 수 있어야 한다 | 기존 ticket_id를 유지하고 결제 처리 단계로 전달 |
| 기능 | 챗봇 인게임 버그 처리 | 버그 판단 결과 저장 | FR-CBOT-BUG-006 | 시스템은 버그 유형 판단 결과를 저장해야 한다 | QA_ticket 또는 ticket_analysis에 자체 버그/미지급 버그 결과 저장 |
|  |  |  |  |  |  |
| 기능 | 챗봇 FAQ 처리 | FAQ 캐시 조회 | FR-CBOT-FAQ-001 | 시스템은 FAQ 응답 생성 전 Redis Cache hit 여부를 확인할 수 있어야 한다 | 반복 FAQ 문의의 응답 속도 개선 |
| 기능 | 챗봇 FAQ 처리 | FAQ 캐시 응답 생성 | FR-CBOT-FAQ-002 | 시스템은 Redis Cache hit 시 캐시된 내용을 기반으로 즉시 답변을 생성할 수 있어야 한다 | 캐시된 FAQ 기반 answer_draft WRITE |
| 기능 | 챗봇 FAQ 처리 | FAQ 캐시 미스 처리 | FR-CBOT-FAQ-003 | 시스템은 Redis Cache miss 시 Vector DB 검색과 Rerank를 수행해야 한다 | Embed → Vector DB → Rerank → Generation 수행 |
| 기능 | 챗봇 FAQ 처리 | FAQ 근거 문서 저장 | FR-CBOT-FAQ-004 | 시스템은 FAQ 답변 생성 시 사용된 근거 문서를 저장해야 한다 | evidence_docs WRITE 수행 |
| 기능 | 챗봇 FAQ 처리 | FAQ 캐시 저장 | FR-CBOT-FAQ-005 | 시스템은 새로 생성된 FAQ 응답을 Redis Cache에 저장할 수 있어야 한다 | TTL 설정 포함 |
|  |  |  |  |  |  |
| 기능 | 챗봇 고객의 소리 처리 | 고객의 소리 접수 응답 생성 | FR-CBOT-VOC-001 | 시스템은 고객의 소리 문의에 대해 접수 안내 메시지를 생성할 수 있어야 한다 | Generation 기반 고정 응대 메시지 생성 |
| 기능 | 챗봇 고객의 소리 처리 | 고객의 소리 데이터 저장 | FR-CBOT-VOC-002 | 시스템은 고객의 소리 원문과 분류 결과를 저장할 수 있어야 한다 | 원문, category, created_at 저장 |
| 기능 | 챗봇 고객의 소리 처리 | 카페 공유 DB 연계 | FR-CBOT-VOC-003 | 시스템은 고객의 소리 데이터를 커뮤니티/운영 공유 DB에 저장할 수 있어야 한다 | 운영자 검토 및 공지 반영용 데이터로 활용 |
|  |  |  |  |  |  |
| 기능 | 챗봇 응답 생성 | 답변 초안 생성 | FR-CBOT-RES-001 | 시스템은 분석 결과와 검색 근거를 기반으로 챗봇 답변 초안을 생성해야 한다 | answer_draft에 draft_text, prompt_version 저장 |
| 기능 | 챗봇 응답 생성 | 근거 문서 연결 | FR-CBOT-RES-002 | 시스템은 챗봇 답변 생성에 사용된 근거 문서를 연결해야 한다 | evidence_docs에 source_id, evidence_text, relevance_score 저장 |
| 기능 | 챗봇 응답 생성 | 프롬프트 버전 저장 | FR-CBOT-RES-003 | 시스템은 챗봇 답변 생성에 사용된 프롬프트 버전을 저장해야 한다 | prompt_version 기준 품질 추적 가능 |
| 기능 | 챗봇 응답 생성 | 고정 응대 메시지 생성 | FR-CBOT-RES-004 | 시스템은 상담원 확인이 필요한 문의에 대해 고정 안내 메시지를 생성할 수 있어야 한다 | 담당자 확인 후 안내드리겠습니다 유형 응답 |
| 기능 | 챗봇 응답 생성 | 상담원 전달 Context 구성 | FR-CBOT-RES-005 | 시스템은 상담원 전달 시 필요한 context를 구성할 수 있어야 한다 | ticket_id, 문의 원문, 분석 결과, 로그 조회 결과, 답변 초안 포함 |
|  |  |  |  |  |  |
| 기능 | 챗봇 Safety Layer | 개인정보 검사 | FR-CBOT-SAFE-001 | 시스템은 챗봇 답변 내 개인정보 포함 여부를 검사할 수 있어야 한다 | answer_draft 대상 PII 검사 수행 |
| 기능 | 챗봇 Safety Layer | 근거 기반 사실성 검사 | FR-CBOT-SAFE-002 | 시스템은 answer_draft와 evidence_docs를 비교해 사실성을 검사할 수 있어야 한다 | Hallucination 및 Factuality 검사 |
| 기능 | 챗봇 Safety Layer | 정책 위반 검사 | FR-CBOT-SAFE-003 | 시스템은 챗봇 답변의 운영 정책 위반 여부를 검사할 수 있어야 한다 | policy_violation_score 산출 |
| 기능 | 챗봇 Safety Layer | 유해 표현 검사 | FR-CBOT-SAFE-004 | 시스템은 챗봇 답변의 욕설 및 유해 표현을 검사할 수 있어야 한다 | toxicity_score 산출 |
| 기능 | 챗봇 Safety Layer | Safety 결과 저장 | FR-CBOT-SAFE-005 | 시스템은 챗봇 답변 검증 결과를 저장해야 한다 | hallucination_score, toxicity_score, policy_violation_score, factuality_score 저장 |
| 기능 | 챗봇 Safety Layer | 사실성 점수 기반 분기 | FR-CBOT-SAFE-006 | 시스템은 factuality_score 기준으로 자동 응답 또는 상담원 검토를 분기할 수 있어야 한다 | 통과 시 자동 응답, 미달 시 상담원 패싱 |
|  |  |  |  |  |  |
| 기능 | 챗봇 자동 응답 처리 | 자동 응답 전달 | FR-CBOT-AUTO-001 | 시스템은 Safety 검증을 통과한 답변을 사용자에게 즉시 전달할 수 있어야 한다 | FAQ 자동 응답 또는 안전성 통과 응답 기준 |
| 기능 | 챗봇 자동 응답 처리 | 상담원 패싱 | FR-CBOT-AUTO-002 | 시스템은 Safety 검증 미달 또는 수동 확인 필요 문의를 상담원에게 전달할 수 있어야 한다 | ticket_id, answer_draft, evidence_docs, safety_results 전달 |
| 기능 | 챗봇 자동 응답 처리 | 최종 처리 상태 갱신 | FR-CBOT-AUTO-003 | 시스템은 자동 응답 또는 상담원 전달 이후 문의 상태를 갱신해야 한다 | QA_ticket.status를 answered, pending_agent, closed 등으로 변경 |
|  |  |  |  |  |  |
| 기능 | 챗봇 상담원 대시보드 연계 | 통합 조회 화면 제공 | FR-CBOT-DASH-001 | 상담원은 챗봇 문의의 원문, 분석 결과, 답변 초안, 로그 조회 결과를 통합 조회할 수 있어야 한다 | QA_ticket, ticket_analysis, answer_draft, payments, refunds, item_delivery_logs JOIN 조회 |
| 기능 | 챗봇 상담원 대시보드 연계 | 상담원 Context 확인 | FR-CBOT-DASH-002 | 상담원은 전달받은 챗봇 문의의 처리 context를 한 화면에서 확인할 수 있어야 한다 | 문의 원문, 분류 결과, 결제/환불/지급 로그, 근거 문서 포함 |
| 기능 | 챗봇 상담원 대시보드 연계 | 수동 처리 지원 | FR-CBOT-DASH-003 | 상담원은 전달받은 챗봇 문의를 기반으로 수동 응대 또는 후속 처리를 수행할 수 있어야 한다 | 결제 확인, 지급 확인, 개발팀 전달 등 |
|  |  |  |  |  |  |
| 기능 | 챗봇 만족도 관리 | 만족도 수집 | FR-CBOT-FBK-001 | 시스템은 자동 응답 이후 사용자 만족도를 수집할 수 있어야 한다 | 별점 또는 만족/불만족 피드백 수집 |
| 기능 | 챗봇 만족도 관리 | 만족도 저장 | FR-CBOT-FBK-002 | 시스템은 수집된 만족도 데이터를 저장해야 한다 | ticket_id, rating, feedback_content, created_at 저장 |
| 기능 | 챗봇 만족도 관리 | 불만족 응답 후속 처리 | FR-CBOT-FBK-003 | 시스템은 불만족 피드백이 접수된 문의를 후속 검토 대상으로 분류할 수 있어야 한다 | 낮은 별점 또는 불만족 선택 시 상담원 검토 큐로 전달 |
|  |  |  |  |  |  |
| 기능 | 챗봇 Observability | 요청 로그 저장 | FR-CBOT-OBS-001 | 시스템은 사용자 입력, SQL 조회, 응답 결과를 기록해야 한다 | Request logging 수행 |
| 기능 | 챗봇 Observability | 모델 호출 로그 저장 | FR-CBOT-OBS-002 | 시스템은 챗봇 응답 생성에 사용된 LLM 호출 이력을 저장해야 한다 | model_name, prompt_version, latency, token_count 저장 |
| 기능 | 챗봇 Observability | 검색 로그 저장 | FR-CBOT-OBS-003 | 시스템은 FAQ/RAG 검색 결과와 점수를 저장해야 한다 | chunk_id, relevance_score, retriever_type 저장 |
| 기능 | 챗봇 Observability | 응답 정확도 추적 | FR-CBOT-OBS-004 | 시스템은 챗봇 응답 정확도를 추적할 수 있어야 한다 | Accuracy tracking 수행 |
| 기능 | 챗봇 Observability | 피드백 루프 | FR-CBOT-OBS-005 | 시스템은 만족도 및 별점 분석 결과를 프롬프트 개선에 활용할 수 있어야 한다 | Feedback loop 기반 prompt 개선 |
| 기능 | 챗봇 Observability | 프롬프트 개선 이력 관리 | FR-CBOT-OBS-006 | 시스템은 프롬프트 개선 이력을 관리할 수 있어야 한다 | 개선 전후 prompt_version 및 성능 지표 저장 |

| 비기능 | 성능 | 챗봇 응답 시간 | NFR-CBOT-PERF-001 | 시스템은 일반 FAQ 문의에 대해 일정 시간 이내 응답을 제공해야 한다 | FAQ Cache hit 기준 3초 이내 응답을 목표로 한다 |
| --- | --- | --- | --- | --- | --- |
| 비기능 | 성능 | RAG 검색 응답 시간 | NFR-CBOT-PERF-002 | 시스템은 Vector DB 검색 및 Rerank 수행 시 지연 시간을 관리해야 한다 | FAQ Cache miss 또는 결제/정책 문서 검색 기준 10초 이내 처리 |
| 비기능 | 성능 | LLM 응답 생성 시간 | NFR-CBOT-PERF-003 | 시스템은 LLM 기반 답변 초안 생성 시간을 추적하고 제한해야 한다 | model latency를 기록하고 임계치 초과 시 상담원 패싱 가능 |
| 비기능 | 성능 | 동시 문의 처리 | NFR-CBOT-PERF-004 | 시스템은 여러 사용자의 챗봇 문의를 동시에 처리할 수 있어야 한다 | 동시 접속 및 동시 문의 상황에서도 응답 지연을 최소화 |
| 비기능 | 성능 | 캐시 기반 응답 최적화 | NFR-CBOT-PERF-005 | 시스템은 반복 FAQ 문의에 대해 Redis Cache를 활용해 응답 속도를 개선해야 한다 | Cache hit rate를 Observability 지표로 관리 |
| 비기능 | 성능 | Cache hit rate 목표 관리 | NFR-CBOT-PERF-006 | 시스템은 Redis Cache hit rate를 성능 지표로 관리하고 목표 수치를 유지해야 한다 | hit rate 임계치 미달 시 운영자 알림, Observability 대시보드에서 확인 가능 |
|  |  |  |  |  |  |
| 비기능 | 가용성 | 챗봇 서비스 지속성 | NFR-CBOT-AVL-001 | 시스템은 챗봇 문의 입력 기능을 안정적으로 제공해야 한다 | 장애 발생 시 사용자에게 안내 메시지 제공 |
| 비기능 | 가용성 | 외부 시스템 장애 대응 | NFR-CBOT-AVL-002 | 시스템은 Vector DB, Redis, LLM API 장애 시 대체 처리 경로를 제공해야 한다 | 장애 시 고정 안내 메시지 또는 상담원 패싱 수행 |
| 비기능 | 가용성 | 상담원 패싱 보장 | NFR-CBOT-AVL-003 | 시스템은 자동 처리 실패 시 상담원에게 문의를 전달할 수 있어야 한다 | 응답 생성 실패, Safety 미달, 로그 조회 실패 시 pending_agent 처리 |
| 비기능 | 가용성 | 부분 장애 허용 | NFR-CBOT-AVL-004 | 시스템은 일부 기능 장애가 전체 챗봇 서비스 중단으로 이어지지 않도록 설계해야 한다 | FAQ, 결제, 버그, VOC 처리 모듈 단위로 장애 격리 |
| 비기능 | 가용성 | 상태 복구 | NFR-CBOT-AVL-005 | 시스템은 장애 복구 후 미처리 티켓을 재처리할 수 있어야 한다 | QA_ticket.status 기준 재시도 대상 식별 |
|  |  |  |  |  |  |
| 비기능 | 확장성 | 문의량 증가 대응 | NFR-CBOT-SCL-001 | 시스템은 챗봇 문의량 증가에 따라 처리 용량을 확장할 수 있어야 한다 | API 서버, Queue, Worker 기반 수평 확장 고려 |
| 비기능 | 확장성 | 처리 모듈 확장 | NFR-CBOT-SCL-002 | 시스템은 신규 문의 유형이 추가될 때 처리 모듈을 확장할 수 있어야 한다 | 결제, 버그, FAQ, VOC 외 신규 카테고리 추가 가능 |
| 비기능 | 확장성 | 지식베이스 확장 | NFR-CBOT-SCL-003 | 시스템은 FAQ, 공지, 정책 문서 증가에 따라 검색 성능을 유지해야 한다 | documents_chunks, documents_embeddings 증가 대응 |
| 비기능 | 확장성 | LLM 모델 교체 가능성 | NFR-CBOT-SCL-004 | 시스템은 LLM 모델 변경 또는 프롬프트 버전 변경에 대응할 수 있어야 한다 | model_name, prompt_version 기반 관리 |
| 비기능 | 확장성 | 채널 확장 가능성 | NFR-CBOT-SCL-005 | 시스템은 챗봇 외 다른 사용자 채널 추가를 고려해 source_type을 확장 가능하게 관리해야 한다 | source_type 기반 채널 구분 구조 유지 |
|  |  |  |  |  |  |
| 비기능 | 보안 | 사용자 인증 보안 | NFR-CBOT-SEC-001 | 시스템은 챗봇 문의자의 사용자 인증 정보를 안전하게 처리해야 한다 | user_id, account_id 연계 시 권한 검증 필요 |
| 비기능 | 보안 | 권한 분리 | NFR-CBOT-SEC-002 | 시스템은 사용자와 상담원/운영자의 접근 권한을 분리해야 한다 | 사용자는 문의 입력만 가능하고 상담원은 관리 화면 접근 가능 |
| 비기능 | 보안 | 개인정보 보호 | NFR-CBOT-SEC-003 | 시스템은 문의 원문, 답변 초안, 로그 내 개인정보를 보호해야 한다 | PII 검사 및 민감정보 마스킹 적용 |
| 비기능 | 보안 | SQL 조회 통제 | NFR-CBOT-SEC-004 | 시스템은 결제·환불·아이템 지급 로그 조회 권한을 통제해야 한다 | 상담원 권한 및 시스템 권한 기준으로 접근 제한 |
| 비기능 | 보안 | 프롬프트 인젝션 방어 | NFR-CBOT-SEC-005 | 시스템은 사용자 입력에 포함된 프롬프트 인젝션 시도를 탐지해야 한다 | 운영 정책 우회, 시스템 명령 노출 유도 문장 검사 |
|  |  |  |  |  |  |
| 비기능 | 개인정보 및 데이터 보호 | 원문 데이터 보호 | NFR-CBOT-PRV-001 | 시스템은 사용자 문의 원문을 안전하게 저장해야 한다 | raw_content 저장 시 접근 권한 제한 |
| 비기능 | 개인정보 및 데이터 보호 | 전처리 데이터 분리 | NFR-CBOT-PRV-002 | 시스템은 원문과 마스킹 처리된 문장을 구분해 관리해야 한다 | raw_content, cleaned_content 분리 관리 |
| 비기능 | 개인정보 및 데이터 보호 | 로그 내 개인정보 최소화 | NFR-CBOT-PRV-003 | 시스템은 Observability 로그에 불필요한 개인정보가 저장되지 않도록 해야 한다 | Request logging 시 민감정보 제거 또는 마스킹 |
| 비기능 | 개인정보 및 데이터 보호 | 데이터 보존 기간 관리 | NFR-CBOT-PRV-004 | 시스템은 문의, 답변, 만족도, 로그 데이터의 보존 기간을 관리해야 한다 | 운영 정책에 따라 저장 기간 및 삭제 기준 정의 |
| 비기능 | 개인정보 및 데이터 보호 | 상담원 화면 개인정보 노출 제한 | NFR-CBOT-PRV-005 | 시스템은 상담원 대시보드에서 필요한 범위의 개인정보만 노출해야 한다 | 결제/환불/계정 정보는 최소 권한 기준 표시 |
|  |  |  |  |  |  |
| 비기능 | 신뢰성 | 응답 근거 신뢰성 | NFR-CBOT-REL-001 | 시스템은 챗봇 답변이 근거 문서와 일치하는지 검증해야 한다 | answer_draft와 evidence_docs 비교 |
| 비기능 | 신뢰성 | Hallucination 방지 | NFR-CBOT-REL-002 | 시스템은 근거 없는 답변 생성을 최소화해야 한다 | hallucination_score 기준 미달 시 상담원 검토 |
| 비기능 | 신뢰성 | 사실성 점수 관리 | NFR-CBOT-REL-003 | 시스템은 답변의 factuality_score를 저장하고 분기 기준으로 활용해야 한다 | 통과 시 자동 응답, 미달 시 상담원 패싱 |
| 비기능 | 신뢰성 | 운영 정책 준수 | NFR-CBOT-REL-004 | 시스템은 챗봇 답변이 게임 운영 정책을 위반하지 않도록 검증해야 한다 | policy_violation_score 산출 |
| 비기능 | 신뢰성 | 결제/지급 판단 신뢰성 | NFR-CBOT-REL-005 | 시스템은 결제 및 미지급 판단 시 실제 운영 로그를 기준으로 처리해야 한다 | payments, refunds, item_delivery_logs 조회 결과 기반 판단 |
|  |  |  |  |  |  |
| 비기능 | 유지보수성 | Prefix 체계 일관성 | NFR-CBOT-MNT-001 | 시스템 요구사항 ID는 NFR-CBOT-[영역코드]-[순번] 형식을 따라야 한다 | FR-CBOT 기능 요구사항과 구분되는 비기능 Prefix 적용 |
| 비기능 | 유지보수성 | 모듈 단위 관리 | NFR-CBOT-MNT-002 | 시스템은 챗봇 기능을 Access, 전처리, 분석, 처리, Safety, Observability 단위로 관리해야 한다 | 영역별 변경 영향 범위 추적 가능 |
| 비기능 | 유지보수성 | 프롬프트 버전 관리 | NFR-CBOT-MNT-003 | 시스템은 답변 생성에 사용된 프롬프트 버전을 관리해야 한다 | prompt_version 기준 성능 비교 및 롤백 가능 |
| 비기능 | 유지보수성 | 모델 호출 이력 관리 | NFR-CBOT-MNT-004 | 시스템은 LLM 모델 호출 이력을 추적 가능하게 저장해야 한다 | model_name, latency, token_count 저장 |
| 비기능 | 유지보수성 | 설정값 관리 | NFR-CBOT-MNT-005 | 시스템은 FAQ 유사도 기준, factuality_score 기준, cache TTL 등 주요 설정값을 관리해야 한다 | 운영 환경별 threshold 조정 가능 |
|  |  |  |  |  |  |
| 비기능 | 관측성 | 요청 로그 저장 | NFR-CBOT-OBS-001 | 시스템은 사용자 입력, SQL 조회, 응답 결과를 로그로 기록해야 한다 | Request logging 수행 |
| 비기능 | 관측성 | 검색 품질 추적 | NFR-CBOT-OBS-002 | 시스템은 FAQ/RAG 검색 결과와 relevance_score를 기록해야 한다 | chunk_id, retriever_type, relevance_score 저장 |
| 비기능 | 관측성 | 응답 품질 추적 | NFR-CBOT-OBS-003 | 시스템은 챗봇 응답의 정확도와 승인 여부를 추적해야 한다 | Accuracy tracking 및 상담원 수정 여부 분석 |
| 비기능 | 관측성 | LLM 비용 추적 | NFR-CBOT-OBS-004 | 시스템은 LLM 호출 token_count를 기록해 비용 분석이 가능해야 한다 | prompt token, completion token, total token 저장 가능 |
| 비기능 | 관측성 | 피드백 루프 관리 | NFR-CBOT-OBS-005 | 시스템은 만족도와 별점 데이터를 프롬프트 개선에 활용해야 한다 | 낮은 만족도 응답을 개선 대상 데이터로 수집 |
|  |  |  |  |  |  |
| 비기능 | 사용성 | 챗봇 입력 편의성 | NFR-CBOT-UX-001 | 시스템은 사용자가 문의 내용을 쉽게 입력할 수 있는 챗봇 UI를 제공해야 한다 | 모바일/웹 환경에서 입력 가능하도록 설계 |
| 비기능 | 사용성 | 응답 이해 가능성 | NFR-CBOT-UX-002 | 시스템은 사용자에게 이해하기 쉬운 문장으로 답변해야 한다 | 게임 CS 응대 톤과 안내형 문장 사용 |
| 비기능 | 사용성 | 상담원 연결 안내 | NFR-CBOT-UX-003 | 시스템은 자동 처리 불가 시 상담원 확인이 필요하다는 안내를 제공해야 한다 | 담당자 확인 후 알려드리겠습니다 유형 메시지 |
| 비기능 | 사용성 | 만족도 입력 편의성 | NFR-CBOT-UX-004 | 시스템은 자동 응답 이후 사용자가 쉽게 만족도를 입력할 수 있어야 한다 | 별점 또는 만족/불만족 버튼 제공 |
| 비기능 | 사용성 | 오류 안내 명확성 | NFR-CBOT-UX-005 | 시스템은 오류 발생 시 사용자에게 명확한 안내 메시지를 제공해야 한다 | 일시적 오류, 상담원 전달, 재시도 안내 구분 |
|  |  |  |  |  |  |
| 비기능 | 운영성 | 상담원 검토 큐 관리 | NFR-CBOT-OPS-001 | 시스템은 상담원 검토가 필요한 문의를 별도 큐로 관리해야 한다 | pending_agent, human_review 상태 관리 |
| 비기능 | 운영성 | 불만족 문의 후속 처리 | NFR-CBOT-OPS-002 | 시스템은 낮은 만족도 피드백이 접수된 문의를 후속 검토 대상으로 분류해야 한다 | 불만족 피드백 발생 시 상담원 검토 큐 연결 |
| 비기능 | 운영성 | 운영 지표 제공 | NFR-CBOT-OPS-003 | 시스템은 챗봇 처리량, 자동 응답률, 상담원 패싱률을 운영 지표로 제공해야 한다 | 대시보드에서 일/주/월 단위 확인 |
| 비기능 | 운영성 | 장애 알림 | NFR-CBOT-OPS-004 | 시스템은 주요 처리 단계 실패 시 운영자에게 알림을 제공해야 한다 | LLM 호출 실패, Vector DB 장애, Redis 장애 등 |
| 비기능 | 운영성 | 수동 처리 이력 추적 | NFR-CBOT-OPS-005 | 시스템은 상담원의 수동 처리 이력을 추적해야 한다 | admin_id, action_type, action_at 저장 |
| 비기능 | 운영성 | 답변 검토 액션 기준 관리 | NFR-CBOT-OPS-006 | 시스템은 상담원의 approved / rejected / edit & approved 액션 기준을 운영 가이드로 관리할 수 있어야 한다 | 무조건 rejected 방지를 위한 점수 기준값 및 운영 지침 명시, 검토 큐 태그 기반 필터링 포함 |
|  |  |  |  |  |  |
| 비기능 | 데이터 정합성 | 티켓 상태 정합성 | NFR-CBOT-DQ-001 | 시스템은 QA_ticket.status가 실제 처리 상태와 일치하도록 관리해야 한다 | answered, pending_agent, closed 등 상태값 관리 |
| 비기능 | 데이터 정합성 | 분석 결과 정합성 | NFR-CBOT-DQ-002 | 시스템은 ticket_analysis의 category와 routing_target이 일관되도록 관리해야 한다 | 카테고리와 처리 모듈 간 불일치 방지 |
| 비기능 | 데이터 정합성 | 근거 문서 연결 정합성 | NFR-CBOT-DQ-003 | 시스템은 answer_draft와 evidence_docs의 연결 관계를 유지해야 한다 | 답변별 source_id, evidence_text 추적 가능 |
| 비기능 | 데이터 정합성 | 결제 로그 조회 정합성 | NFR-CBOT-DQ-004 | 시스템은 결제 문의 처리 시 account_id 기준으로 관련 로그를 조회해야 한다 | payments, refunds, item_delivery_logs 간 연결 오류 방지 |
| 비기능 | 데이터 정합성 | 중복 문의 관리 | NFR-CBOT-DQ-005 | 시스템은 동일 사용자의 반복 문의를 식별할 수 있어야 한다 | user_id, account_id, category, created_at 기준 중복성 판단 |
|  |  |  |  |  |  |
| 비기능 | 감사 및 추적성 | 처리 흐름 추적 | NFR-CBOT-AUD-001 | 시스템은 사용자 문의가 어떤 처리 경로를 거쳤는지 추적할 수 있어야 한다 | FAQ, 결제, 버그, VOC, 상담원 패싱 경로 기록 |
| 비기능 | 감사 및 추적성 | 응답 생성 근거 추적 | NFR-CBOT-AUD-002 | 시스템은 챗봇 답변 생성에 사용된 근거 문서를 추적할 수 있어야 한다 | evidence_docs와 source document 연결 |
| 비기능 | 감사 및 추적성 | Safety 검증 이력 추적 | NFR-CBOT-AUD-003 | 시스템은 Safety 검증 결과와 분기 사유를 추적할 수 있어야 한다 | 검증 점수, 통과/미달 여부, 상담원 패싱 사유 저장 |
| 비기능 | 감사 및 추적성 | 상담원 조치 이력 추적 | NFR-CBOT-AUD-004 | 시스템은 상담원이 수행한 수정, 반려, 수동 처리 이력을 저장해야 한다 | admin_id, action_type, action_at, edited_reason 저장 |
| 비기능 | 감사 및 추적성 | 프롬프트 개선 이력 추적 | NFR-CBOT-AUD-005 | 시스템은 프롬프트 개선 전후 변경 이력을 추적할 수 있어야 한다 | prompt_version, 변경 사유, 성능 지표 저장 |