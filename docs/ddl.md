## ERD

**RDBMS**

- DDL
    
    ```smalltalk
    Table community_users {
      user_id int [pk]
      email varchar
      nickname varchar
      created_at datetime
      user_status varchar
      last_login_at datetime
    }
    Table game_accounts {
      account_id int [pk]
      user_id int [ref: > community_users.user_id]
      game_name varchar
      uid varchar
      server_region varchar
      progression_level int
      account_status varchar
      created_at datetime
    }
    Table QA_ticket {
      ticket_id int [pk]
      account_id int [ref: > game_accounts.account_id, null]
      user_id int [ref: > community_users.user_id]
      title varchar
      raw_content text
      source_type varchar
      responder_type varchar
      status varchar
      inquiry_created_at datetime
    }
    Table ticket_analysis {
      analysis_id int [pk]
      ticket_id int [ref: > QA_ticket.ticket_id]
      category varchar
      responder_type varchar
      content text
      risk_level varchar
      sentiment varchar
      relevance_score float
      routing_target varchar
      summary text
      analyzed_at datetime
    }
    Table payments {
      payment_id int [pk]
      account_id int [ref: > game_accounts.account_id]
      product_name varchar
      product_type varchar
      amount decimal
      currency varchar
      payment_method varchar
      payment_status varchar
      transaction_id varchar
      paid_at datetime
    }
    Table refunds {
      refund_id int [pk]
      payment_id int [ref: > payments.payment_id]
      refund_status varchar
      refund_reason text
      requested_at datetime
      processed_at datetime
    }
    Table item_delivery_logs {
      delivery_id int [pk]
      payment_id int [ref: > payments.payment_id, null]
    
      account_id int [ref: > game_accounts.account_id]
      source_type varchar
      item_name varchar
      quantity int
      delivery_status varchar
      expected_at datetime
      delivered_at datetime
    }
    Table gacha_logs {
      gacha_id int [pk]
      account_id int [ref: > game_accounts.account_id]
      banner_name varchar
      item_name varchar
      item_type varchar
      rarity varchar
      pity_count int
      pulled_at datetime
    }
    Table answer_draft {
      draft_id int [pk]
      ticket_id int [ref: > QA_ticket.ticket_id]
      analysis_id int [ref: > ticket_analysis.analysis_id]
      draft_text text
      prompt_version varchar
      created_at datetime
    }
    Table evidence_docs {
      evidence_id int [pk]
      draft_id int [ref: > answer_draft.draft_id]
      source_type varchar
      source_id varchar
      evidence_text text
      relevance_score float
      retrieval_rank int
    }
    Table safety_results {
      safety_id int [pk]
      draft_id int [ref: > answer_draft.draft_id]
      hallucination_score float
      toxicity_score float
      policy_violation_score float
      factuality_score float
      checked_at datetime
    }
    Table insight {
      insight_id int [pk]
      user_id int [ref: > community_users.user_id]
      ticket_id int [ref: > QA_ticket.ticket_id]
      account_id int [ref: > game_accounts.account_id, null]
      content_summary text
      category varchar
      sentiment varchar
      risk_level varchar
      pattern_risk_level varchar
      inquiry_created_at datetime
    }
    
    ```
    
- 예시 데이터
    
    **community_users - 커뮤니티 계정**
    
    | user_id | email | nickname | created_at | user_status | last_login_at |
    | --- | --- | --- | --- | --- | --- |
    | 1 | [user1@game.com](mailto:user1@game.com) | FireMage | 2026-05-01 09:00:00 | active | 2026-05-11 22:10:00 |
    | 2 | [user2@game.com](mailto:user2@game.com) | ShadowFox | 2026-05-02 11:20:00 | suspended | 2026-05-10 18:00:00 |
    | int | varchar | varchar | datetime | varchar | datetime |
    | 커뮤니티 회원 ID | 커뮤니티 가입 이메일 | 커뮤니티 닉네임 | 커뮤니티 가입일 | 계정 상태 | 마지막 로그인 일시 |
    
    **game_accounts -  게임 계정**
    
    | account_id | user_id | game_name | uid | server_region | progression_level | account_status | created_at |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | 101 | 1 | genshin impact | 8123456 | KR | 57 | active | 2026-05-01 09:10:00 |
    | 102 | 2 | starrail | 18789012 | JP | 34 | active | 2026-05-02 11:30:00 |
    | int | int | varchar | varchar | varchar | int | varchar | datetime |
    | 게임 계정 ID | 커뮤니티 회원 ID | 게임명 | 게임 고유 UID | 서버 권역 | 게임 진행 레벨 | 게임 계정 상태 | 게임 계정 생성일 |
    
    **QA_ticket - 챗봇 대화 & 커뮤니티 게시글 원문 테이블**
    
    | ticket_id | account_id | user_id | title | raw_content | source_type | responder_type | status | inquiry_created_at |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 1001 | 101 | 1 | 결제 후 아이템 미지급 | 결제는 완료됐는데 아이템이 안 들어왔어요 | community | AI | open | 2026-05-11 10:00:00 |
    | 1002 | 102 | 2 | NULL | Q: 암튼 안돼요 / A: 어떤 문제가 발생했는지 확인이 필요합니다 | chatbot | human | pending | 2026-05-11 11:30:00 |
    | int | int | int | varchar | text | varchar | varchar | varchar | datetime |
    | 문의 ID | 관련 게임 계정 ID | 문의 작성 커뮤니티 회원 ID | 문의 제목 | 문의 원문 | 유입 채널 | 응답 주체 | 처리 상태 | 문의 발생일 |
    
    **ticket_analysis  -문의 분석 테이블**
    
    | analysis_id | ticket_id | category | responder_type | content | risk_level | sentiment | relevance_score | routing_target | summary | analyzed_at |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 5001 | 1001 | payment | AI | 결제는 완료됐는데 아이템이 안 들어왔어요 | HIGH | negative | 0.97 | urgent_alert | 결제 완료 대비 지급 로그 누락 가능성 | 2026-05-11 10:03:00 |
    | 5002 | 1002 | gacha | human | 가챠 결과가 이상하다는 문의 | LOW | neutral | 0.82 | rag_reply | 확률형 아이템 정책 문의 | 2026-05-11 11:35:00 |
    | int | int | varchar | varchar | text | varchar | varchar | float | varchar | text | datetime |
    | 분석 ID | 문의 ID | 문의 유형 | 권장 응답 주체 | 챗봇과 게시글 모두 이 위치에서 전처리되었음을 상정한다.
      • 전처리란?
      • 챗봇 : 요약
      • 게시글 : 답변 생성을 위한 전처리된 문장 | 위험도, LLM이 만들어줌 | 감성 분석 결과, LLM이 만들어줌 | 근거 문서와의 관련도, RAG로 찾은 evidence docs와 생성된 문장의 연관도 점수 | 라우팅 대상, RAG로 답변 가능한건 rag_reply로 전달
    
    답변불가는 urgent_alert로 이동 | 분석 요약, 인사이트 대시보드 만들 때 활용할 텍스트 | 분석 일시 |
    
    **payments - 결제 내역 테이블**
    
    | payment_id | account_id | product_name | product_type | amount | currency | payment_method | payment_status | transaction_id | paid_at |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 7001 | 101 | 스타터_패키지 | package | 9900 | KRW | card | success | TXN12345 | 2026-05-11 09:55:00 |
    | 7002 | 102 | 다이아_200개 | currency | 55000 | KRW | google_pay | fail | TXN67890 | 2026-05-11 11:00:00 |
    | int | int | varchar | varchar | decimal | varchar | varchar | varchar | varchar | datetime |
    | 결제 ID | 결제한 게임 계정 ID | 상품명 | 상품 유형 | 결제 금액 | 통화 | 결제 수단 | 결제 상태 | 외부 결제 거래 ID | 결제 일시 |
    
    **refunds - 환불 내역**
    
    | refund_id | payment_id | refund_status | refund_reason | requested_at | processed_at |
    | --- | --- | --- | --- | --- | --- |
    | 9501 | 7001 | pending | 아이템 미지급 | 2026-05-11 10:20:00 | NULL |
    | 9502 | 7002 | completed | 결제 실패 후 청구 확인 | 2026-05-11 11:20:00 | 2026-05-11 16:30:00 |
    | int | int | varchar | text | datetime | datetime |
    | 환불 ID | 결제 ID | 환불 여부 | 환불 사유 | 환불 요청일 | 환불 처리일
      • pending 일때는 null값 |
    
    **item_delivery_logs -지급 내역**
    
    | delivery_id | payment_id | account_id | source_type | item_name | quantity | delivery_status | expected_at | delivered_at |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 8001 | 7001 | 101 | payment_reward | 스타터 패키지 상자 | 1 | fail | 2026-05-11 10:01:00 | NULL |
    | 8002 | NULL | 102 | event_reward | SSR 소환권 | 3 | delivered | 2026-05-10 18:00:00 | 2026-05-10 18:01:00 |
    | int | int | int | varchar | varchar | int | varchar | datetime | datetime |
    | 지급 로그 ID | 관련 결제 ID | 지급 대상 게임 계정 ID | 지급 발생 유형 | 지급 아이템명 | 수량 | 지급 상태 | 지급 예정·시도 일시 | 실제 지급 일시 |
    
    **gacha_logs - 가챠 로그**
    
    | gatcha_id | account_id | banner_name | item_name | item_type | rarity | pity_count | pulled_at |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | 9001 | 101 | 봄 축제 픽업 | 화염의 검 | weapon | 4성 | 72 | 2026-05-11 08:00:00 |
    | 9002 | 102 | 전설 영웅 소환 | 그림자 마법사 | character | 5성 | 34 | 2026-05-11 11:10:00 |
    | int | int | varchar | varchar | varchar | varchar | int | datetime |
    | 가챠 id   | 가챠시도한 계정 id | 가차 종류 | 가챠에서 뽑은 아이템 이름 | 무기인지 캐릭터인지(가챠 속성) | 아이템 등급 | 누적치 임계 확정 획득(픽뚫) | 뽑은 날짜 |
    
    **answer_draft - 답변 초안**
    
    | draft_id | ticket_id | analysis_id | draft_text | prompt_version | created_at |
    | --- | --- | --- | --- | --- | --- |
    | 3001 | 1001 | 5001 | 결제 내역 확인 후 아이템 지급 상태를 확인하겠습니다. | v2_payment_prompt | 2026-05-11 10:05:00 |
    | 3002 | 1002 | 5002 | 가챠 확률은 공지된 확률 정책에 따라 적용됩니다. | v1_gacha_prompt | 2026-05-11 11:40:00 |
    | int | int | int | text | varchar | datetime |
    | 답변 초안 ID | 문의 ID | 분석 ID | 생성된 답변 초안 | 사용 프롬프트 버전 | 초안 생성일 |
    
    **evidence_docs _ 근거 문서**
    
    | evidence_id | draft_id | source_type | source_id | evidence_text | relevance_score | retrieval_rank |
    | --- | --- | --- | --- | --- | --- | --- |
    | 4001 | 3001 | FAQ | FAQ-101 | 결제 후 최대 5분 내 아이템 지급이 진행됩니다. | 0.94 | 1 |
    | 4002 | 3002 | NOTICE | NOTICE-77 | 확률형 아이템 확률은 공지된 정책에 따라 공개됩니다. | 0.89 | 1 |
    | int | int | varchar | varchar | text | float | int |
    | 근거 문서 ID | 답변 초안 ID | 문서 출처 유형 | 출처 문서 ID | 검색된 근거 문장 | 검색 관련도 점수 | 검색 순위 |
    
    **safety_results - 답변 안전성 점검 테이블**
    
    | safety_id | draft_id | hallucination_score | toxicity_score | policy_violation_score | factuality_score |
    | --- | --- | --- | --- | --- | --- |
    | 6001 | 3001 | 0.03 | 0.00 | 0.01 | 0.98 |
    | 6002 | 3002 | 0.07 | 0.00 | 0.00 | 0.95 |
    | int | int | float | float | float | float |
    | 식별자용 ID | answer draft id 가져옴 | 환각 점수 | 유해  점수 | 정책 위반 점수 | 옆 3개 지표 가중평균 |
    
    **insights - 운영 인사이트**
    
    | insight_id | user_id | ticket_id | account_id | content_summary | category | sentiment | risk_level | pattern_risk_level | inquiry_created_at |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 11001 | 1 | 1001 | 101 | 동일 결제 미지급 문의 반복 증가 | payment | negative | HIGH | CRITICAL | 2026-05-11 10:00:00 |
    | 11002 | 2 | 1002 | 102 | 가챠 확률 관련 문의 증가 추세 | gacha | neutral | LOW | MEDIUM | 2026-05-11 11:30:00 |
    | int | int | int | int | text | varchar | varchar | varchar | varchar | datetime |
    | 인사이트 ID | 커뮤니티 회원 ID | 문의 ID | 관련 게임 계정 ID | 운영 인사이트 요약 | 문의 유형 | 감성 분석 결과 | 단일 문의 위험도 | 반복 패턴 기반 위험도 | 문의 발생일 |
    

https://dbdiagram.io/d/RDBMS-6a02741e7a923b947283d7bf

**Vector DB(3개)**

- DDL
    
    ```smalltalk
    
    Table documents {
      documents_id varchar [pk]
      source_type varchar
      category varchar
      title varchar
      raw_content text
      source_url varchar
      published_at datetime
      updated_at datetime
    }
    
    Table documents_chunks {
      chunk_id varchar [pk]
      document_id varchar [ref: > documents.documents_id]
      chunk_text text
      chunk_order int
      token_count int
      created_at datetime
    }
    
    Table documents_embeddings {
      embedding_id varchar [pk]
      chunk_id varchar [ref: > documents_chunks.chunk_id]
      embedding_vector vector
      embedding_model varchar
      source_type varchar
      category varchar
      created_at datetime
    }
    
    Ref: "documents_embeddings"."embedding_id" < "documents_embeddings"."created_at"
    ```
    
- 예시 데이터
    
    **documents**
    
    | documents_id | source_type | category | title | raw_content | source_url | published_at | updated_at |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | ASDF-1 | FAQ | payment | 결제 오류 대응 가이드 | 결제 오류 발생 시 대응 절차 | https://docs.game.com/faq1 | 2026-05-01 10:00:00 | 2026-05-01 11:00:00 |
    |  | NOTICE | event | 이벤트 보상 지급 안내 | 이벤트 보상 지급 관련 공지 | https://docs.game.com/n1 | 2026-05-03 09:00:00 | 2026-05-03 09:30:00 |
    | varchar | varchar | varchar | varchar | text | varchar | datetime | datetime |
    | 아이디 | 수집위치 | 크롤링 기준 카테고리 | 크롤링 기준 제목 | 크롤링 기준 본문 | 크롤링 링크 | 올린 날짜 | 수정 날짜 |
    
    **documents_chunks**
    
    | chunk_id | document_id | chunk_text | chunk_order | token_count | created_at |
    | --- | --- | --- | --- | --- | --- |
    | ASDF-1-43 |  | 결제 오류 발생 시 앱을 재실행해주세요. | 1 | 32 | 2026-05-01 10:05:00 |
    | ASDF-1-44 |  | 중복 결제는 영업일 기준 3일 내 처리됩니다. | 2 | 41 | 2026-05-01 10:05:30 |
    | ASDF-1-42 | ASDF-1 | 이벤트 보상은 순차 지급됩니다. | 1 | 25 | 2026-05-03 09:10:00 |
    | 출신문서 아이디-순서표기로 유니크 아이디 작성 | 출신 문서 아이디 | 그냥 텍스트 | 본문 내 몇 번째인지 | 총 토큰 개수 | 생성 날짜 |
    | varchar | varchar | text | int | int | datetime |
    
    **documents_embeddings**
    
    | embedding_id | chunk_id | embedding_vector | embedding_model | source_type | category | created_at |
    | --- | --- | --- | --- | --- | --- | --- |
    | ASDF-1-42-E | ASDF-1-43 | [0.123,0.532,...] | bge-m3 | FAQ | payment | 2026-05-01 10:06:00 |
    | 1002ASDF-1-42-E | ASDF-1-44 | [0.231,0.884,...] | bge-m3 | FAQ | payment | 2026-05-01 10:06:10 |
    | 1003ASDF-1-42-E | ASDF-1-42 | [0.912,0.112,...] | bge-m3 | NOTICE | event | 2026-05-03 09:11:00 |
    | 문서 청크 아이디 +E | 문서 청크 아이디 | 벡터값 | 임베딩 모델 | 모르겟슴 | 모르겟슴 |  |
    | varchar | varchar | vector | varchar | varchar | varchar | datetime |
    

https://dbdiagram.io/d/vector-DB-6a02747954a51d93d3fb065e