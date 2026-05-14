- 운영배치 머메이드
    
    ### 전체 요약 흐름
    
    ```mermaid
    flowchart TB
    
    POST["게시글 예시<br/><br/>
    결제 후 아이템 미지급<br/>
    결제는 완료됐는데 아이템이 안 들어왔어요"]
    
    DATA["Data Layer<br/><br/>
    QA_ticket 저장<br/>
    계정 / 결제 / 지급 로그 조회<br/>
    Vector DB 검색 준비"]
    
    STEP1["STEP1<br/>문의 유형 및 리스크 분석"]
    
    STEP2["STEP2<br/>답변 초안 생성"]
    
    APPROVAL["Approval Gate<br/>답변 안전성 검증"]
    
    HUMAN["Human-in-the-loop<br/>운영자 최종 검수"]
    
    STEP3["STEP3<br/>운영 인사이트 생성"]
    
    OBS["Observability Gate<br/>운영 모니터링"]
    
    POST --> DATA --> STEP1 --> STEP2 --> APPROVAL --> HUMAN --> STEP3 --> OBS
    
    classDef source fill:#fff7e6,stroke:#d48806,color:#000;
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    classDef gate fill:#fff4cc,stroke:#c9a400,color:#000,stroke-width:2px;
    classDef obs fill:#e8fff7,stroke:#00a37a,color:#000;
    
    class POST source;
    class DATA db;
    class STEP1,STEP2,HUMAN,STEP3 step;
    class APPROVAL gate;
    class OBS obs;
    ```
    
    ### **Data Layer 상세 구조**
    
    ```mermaid
    flowchart TB
    
    POST["커뮤니티 게시글 / 챗봇 문의"]
    
    PIPE1["수집 파이프라인<br/><br/>
    title<br/>
    raw_content<br/>
    source_type<br/>
    user_id<br/>
    account_id"]
    
    QA["RDBMS · QA_ticket<br/><br/>
    문의 원문 저장<br/><br/>
    ticket_id<br/>
    user_id<br/>
    account_id nullable<br/>
    title<br/>
    raw_content<br/>
    source_type<br/>
    responder_type<br/>
    status<br/>
    inquiry_created_at"]
    
    IDENTITY["계정 식별 파이프라인<br/><br/>
    QA_ticket.user_id<br/>
    → community_users.user_id<br/><br/>
    QA_ticket.account_id<br/>
    → game_accounts.account_id"]
    
    CU["RDBMS · community_users<br/><br/>
    커뮤니티 계정 정보<br/><br/>
    user_id<br/>
    email<br/>
    nickname<br/>
    user_status<br/>
    last_login_at"]
    
    GA["RDBMS · game_accounts<br/><br/>
    게임 계정 정보<br/><br/>
    account_id<br/>
    user_id<br/>
    game_name<br/>
    uid<br/>
    server_region<br/>
    progression_level<br/>
    account_status"]
    
    PIPE2["업무 로그 조회 파이프라인<br/><br/>
    account_id 기준 조회"]
    
    PAY["RDBMS · payments<br/><br/>
    결제 로그<br/><br/>
    payment_id<br/>
    account_id<br/>
    product_name<br/>
    amount<br/>
    payment_status<br/>
    transaction_id<br/>
    paid_at"]
    
    REF["RDBMS · refunds<br/><br/>
    환불 로그<br/><br/>
    refund_id<br/>
    payment_id<br/>
    refund_status<br/>
    refund_reason"]
    
    ITEM["RDBMS · item_delivery_logs<br/><br/>
    아이템 지급 로그<br/><br/>
    delivery_id<br/>
    payment_id nullable<br/>
    account_id<br/>
    source_type<br/>
    item_name<br/>
    delivery_status<br/>
    delivered_at"]
    
    GACHA["RDBMS · gacha_logs<br/><br/>
    가챠 로그<br/><br/>
    gacha_id<br/>
    account_id<br/>
    banner_name<br/>
    item_name<br/>
    rarity<br/>
    pity_count"]
    
    DOC["Vector DB · documents<br/><br/>
    FAQ / 공지 / 정책 원문"]
    
    CHUNK["Vector DB · documents_chunks<br/><br/>
    문서 chunk 저장<br/><br/>
    chunk_id<br/>
    document_id<br/>
    chunk_text<br/>
    token_count"]
    
    EMBED["Vector DB · documents_embeddings<br/><br/>
    임베딩 저장<br/><br/>
    embedding_id<br/>
    chunk_id<br/>
    embedding_vector<br/>
    embedding_model"]
    
    POST --> PIPE1 --> QA
    QA --> IDENTITY
    IDENTITY --> CU
    IDENTITY --> GA
    GA --> PIPE2
    PIPE2 --> PAY
    PIPE2 --> REF
    PIPE2 --> ITEM
    PIPE2 --> GACHA
    
    DOC --> CHUNK --> EMBED
    
    classDef source fill:#fff7e6,stroke:#d48806,color:#000;
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    
    class POST source;
    class QA,CU,GA,PAY,REF,ITEM,GACHA,DOC,CHUNK,EMBED db;
    class PIPE1,PIPE2,IDENTITY step;
    ```
    
    ### **STEP1 · 문의 유형 분석 및 Query Routing**
    
    ```mermaid
    flowchart TB
    
    QA["RDBMS · QA_ticket<br/><br/>
    ticket_id: 1001<br/>
    title: 결제 후 아이템 미지급<br/>
    raw_content: 결제는 완료됐는데 아이템이 안 들어왔어요<br/>
    user_id: 1<br/>
    account_id: 101"]
    
    ROUTER["첫 Query Routing<br/><br/>
    결제 / 환불 / 미지급<br/>
    가챠 / 확률<br/>
    운영 정책<br/>
    욕설 / 장애 감지"]
    
    BRANCH{"문의 유형 분기"}
    
    CU["community_users 조회<br/><br/>
    user_id = 1"]
    
    GA["game_accounts 조회<br/><br/>
    account_id = 101"]
    
    PAY["payments 조회<br/><br/>
    account_id = 101<br/>
    payment_status = success"]
    
    ITEM["item_delivery_logs 조회<br/><br/>
    payment_id = 7001<br/>
    delivery_status = fail"]
    
    REF["refunds 조회<br/><br/>
    payment_id = 7001"]
    
    ANALYZER["LLM 분석기<br/><br/>
    category 생성<br/>
    risk_level 생성<br/>
    sentiment 생성<br/>
    routing_target 생성"]
    
    ANALYSIS["RDBMS · ticket_analysis<br/><br/>
    analysis_id: 5001<br/>
    ticket_id: 1001<br/>
    category: payment<br/>
    risk_level: HIGH<br/>
    sentiment: negative<br/>
    routing_target: urgent_alert<br/>
    summary: 결제 완료 대비 지급 로그 누락 가능성"]
    
    QA --> ROUTER --> BRANCH
    
    BRANCH -->|"결제 / 미지급"| CU
    CU --> GA
    GA --> PAY
    PAY --> ITEM
    PAY --> REF
    
    ITEM --> ANALYZER
    REF --> ANALYZER
    
    ANALYZER --> ANALYSIS
    
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    classDef gate fill:#fff4cc,stroke:#c9a400,color:#000,stroke-width:2px;
    
    class QA,ANALYSIS,CU,GA,PAY,ITEM,REF db;
    class ROUTER,ANALYZER step;
    class BRANCH gate;
    ```
    
    ### **STEP2 · RAG 검색 및 답변 생성**
    
    ```mermaid
    flowchart TB
    
    ANALYSIS["RDBMS · ticket_analysis<br/><br/>
    routing_target: urgent_alert"]
    
    ROUTE{"routing_target 확인"}
    
    RAG["Hybrid Retriever<br/><br/>
    BM25 + Vector Search"]
    
    EMBED["Vector DB · documents_embeddings<br/><br/>
    embedding similarity search"]
    
    CHUNK["Vector DB · documents_chunks<br/><br/>
    관련 chunk 조회"]
    
    DOC["Vector DB · documents<br/><br/>
    FAQ / 공지 / 정책 원문 조회"]
    
    DRAFT["RDBMS · answer_draft<br/><br/>
    draft_id: 3001<br/>
    ticket_id: 1001<br/>
    analysis_id: 5001<br/>
    draft_text 생성<br/>
    prompt_version 저장"]
    
    EVIDENCE["RDBMS · evidence_docs<br/><br/>
    draft_id: 3001<br/>
    source_type: FAQ<br/>
    source_id: FAQ-101<br/>
    evidence_text 저장<br/>
    relevance_score 저장"]
    
    ANALYSIS --> ROUTE
    
    ROUTE -->|"rag_reply"| RAG
    ROUTE -->|"urgent_alert"| DRAFT
    
    RAG --> EMBED
    EMBED --> CHUNK
    CHUNK --> DOC
    
    DOC --> DRAFT
    DOC --> EVIDENCE
    
    DRAFT --> EVIDENCE
    
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    classDef gate fill:#fff4cc,stroke:#c9a400,color:#000,stroke-width:2px;
    
    class ANALYSIS,EMBED,CHUNK,DOC,DRAFT,EVIDENCE db;
    class RAG step;
    class ROUTE gate;
    ```
    
    ### Approval Gate + Human-in-the-loop
    
    ```mermaid
    flowchart TB
    
    DRAFT["RDBMS · answer_draft"]
    
    EVIDENCE["RDBMS · evidence_docs"]
    
    CHECK["답변 안전성 검사<br/><br/>
    근거 문서 일치 여부<br/>
    Hallucination 여부<br/>
    정책 위반 여부<br/>
    욕설 / 유해 표현 여부"]
    
    SAFETY["RDBMS · safety_results<br/><br/>
    hallucination_score<br/>
    toxicity_score<br/>
    policy_violation_score<br/>
    factuality_score"]
    
    RESULT{"승인 결과"}
    
    HUMAN["운영자 검수<br/><br/>
    답변 수정<br/>
    수동 지급<br/>
    환불 처리<br/>
    긴급 대응"]
    
    FINAL["최종 응답 게시<br/><br/>
    QA_ticket.status = closed"]
    
    DRAFT --> CHECK
    EVIDENCE --> CHECK
    
    CHECK --> SAFETY
    SAFETY --> RESULT
    
    RESULT -->|"approved"| FINAL
    RESULT -->|"human_review"| HUMAN
    RESULT -->|"urgent_alert"| HUMAN
    
    HUMAN --> FINAL
    
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    classDef gate fill:#fff4cc,stroke:#c9a400,color:#000,stroke-width:2px;
    
    class DRAFT,EVIDENCE,SAFETY db;
    class CHECK,HUMAN,FINAL step;
    class RESULT gate;
    ```
    
    ### STEP3 · 운영 인사이트 및 Observability
    
    ```mermaid
    flowchart TB
    
    ANALYSIS["RDBMS · ticket_analysis"]
    
    SAFETY["RDBMS · safety_results"]
    
    FINAL["최종 응답 결과"]
    
    AGG["운영 통계 집계<br/><br/>
    동일 문의 반복 여부<br/>
    감성 변화 추이<br/>
    위험 키워드 증가율"]
    
    INSIGHT["RDBMS · insight<br/><br/>
    insight_id<br/>
    user_id<br/>
    ticket_id<br/>
    account_id nullable<br/>
    content_summary<br/>
    category<br/>
    sentiment<br/>
    risk_level<br/>
    pattern_risk_level"]
    
    OBS["Observability Layer"]
    
    M1["결제 미지급 증가율"]
    
    M2["HIGH 위험 문의 수"]
    
    M3["재문의율"]
    
    M4["운영자 수정 비율"]
    
    M5["답변 승인율"]
    
    M6["Slack / Discord Alert"]
    
    ANALYSIS --> AGG
    SAFETY --> AGG
    FINAL --> AGG
    
    AGG --> INSIGHT
    
    INSIGHT --> OBS
    
    OBS --> M1
    OBS --> M2
    OBS --> M3
    OBS --> M4
    OBS --> M5
    OBS --> M6
    
    classDef db fill:#e8f0ff,stroke:#5b8def,color:#000,stroke-width:1.5px;
    classDef step fill:#f5f5f5,stroke:#888,color:#000;
    classDef obs fill:#e8fff7,stroke:#00a37a,color:#000;
    
    class ANALYSIS,SAFETY,INSIGHT db;
    class AGG,FINAL step;
    class OBS,M1,M2,M3,M4,M5,M6 obs;
    ```