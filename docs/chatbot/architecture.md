# Chatbot Workflow Mermaid

이 문서는 챗봇의 최종 workflow를 Mermaid 기준으로 정리합니다.

현재 메인 실행 경로는 `chatbot/agent.py`의 LangChain `create_agent`이며, 이 폴더의 `workflow.py`는 LangGraph `StateGraph` 전환을 위한 실험 경로입니다. 최종 설계에서는 `StateGraph`가 전체 처리 순서와 분기를 관리하고, 각 node 내부에서 tools 또는 agent 로직을 사용합니다.

## Workflow

```mermaid
flowchart TD
    USER([User]) --> ACCESS

    subgraph ACCESS["Step 1. Access Layer"]
        A1["Chatbot Interface<br/>사용자 문의 입력"]
        A2["Session Manager<br/>user_id, session_id, 대화 이력 관리"]
        A3["Input Payload 생성<br/>raw_content, source_type, account_id"]
        A1 --> A2 --> A3
    end

    ACCESS --> ORCH

    subgraph ORCH["Step 2. Orchestration Layer"]
        O1["Toxic Filter<br/>욕설 / 위협 / 유해표현 1차 감지"]
        O2["Input Normalize<br/>cleaned_content 생성"]
        O3["Query Enrichment<br/>분류 힌트 보강"]
        O4["Classifier<br/>category, routing_target 결정"]
        O5["QA_ticket WRITE"]
        O6["ticket_analysis WRITE"]
        O7{"Category Routing"}

        O1 --> O2 --> O3 --> O4 --> O5 --> O6 --> O7
    end

    O7 -->|"FAQ"| FAQ
    O7 -->|"인게임버그"| BUG
    O7 -->|"결제"| PAY
    O7 -->|"VOC"| VOC

    subgraph INTEL["Step 3. Intelligence Layer"]
        subgraph FAQ["FAQ Agent"]
            F1{"Cache Hit?"}
            F2["Cache Answer<br/>answer_draft WRITE"]
            F3["RAG Search<br/>Embed → Search → Rerank"]
            F4["Answer Generation<br/>answer_draft WRITE<br/>evidence_docs WRITE"]
            F5{"답변 가능?"}
            F6["failed_queries WRITE<br/>FAQ/RAG 실패 사유 저장"]

            F1 -->|"Hit"| F2
            F1 -->|"Miss"| F3 --> F4
            F2 --> F5
            F4 --> F5
            F5 -->|"가능"| SAFETY
            F5 -->|"불가"| F6 --> OPDATA
        end

        subgraph BUG["Bug Agent"]
            B1["Data Lookup<br/>gacha_logs / item_delivery_logs READ"]
            B2{"버그 유형 판단"}
            B3["단순 버그<br/>answer_draft WRITE"]
            B4["복잡 버그<br/>operator_queue WRITE"]
            B5["미지급 의심<br/>Payment Agent로 전달"]

            B1 --> B2
            B2 -->|"단순"| B3 --> SAFETY
            B2 -->|"복잡"| B4 --> OPDATA
            B2 -->|"미지급"| B5 --> PAY
        end

        subgraph PAY["Payment Agent"]
            P1["Data Lookup<br/>payments / refunds / item_delivery_logs READ"]
            P2{"routing_target"}
            P3["rag_reply<br/>answer_draft WRITE<br/>evidence_docs WRITE"]
            P4["urgent_alert<br/>operator_queue WRITE<br/>answer_draft WRITE"]

            P1 --> P2
            P2 -->|"rag_reply"| P3 --> SAFETY
            P2 -->|"urgent_alert"| P4 --> OPDATA
        end

        subgraph VOC["VOC Agent"]
            V1["VOC Type Classifier<br/>건의 / 불만 / 칭찬 / 기타"]
            V2["VOC_DB WRITE"]
            V3["고정 접수 답변<br/>answer_draft WRITE"]

            V1 --> V2 --> OPDATA
            V2 --> V3 --> FINAL
        end
    end

    subgraph SAFETY["Step 4. Safety Layer"]
        S1["Safety Checks<br/>PII Detection<br/>Response Validation<br/>Moderation"]
        S2["safety_results WRITE<br/>decision_type, factuality, hallucination,<br/>toxicity, pii_detected, reason"]
        S3{"final_decision"}

        S4["AUTO_RESPONSE<br/>답변 승인"]
        S5["MASKING<br/>개인정보 마스킹 후 재검사"]
        S6["SAFE_FALLBACK<br/>고정 안내문 또는 재생성 요청"]
        S7["BLOCK_RESPONSE<br/>차단 안내 답변"]
        S8["REVIEW_QUEUE<br/>operator_queue WRITE"]

        S1 --> S2 --> S3
        S3 -->|"AUTO_RESPONSE"| S4 --> FINAL
        S3 -->|"MASKING"| S5 --> S1
        S3 -->|"SAFE_FALLBACK"| S6 --> FINAL
        S3 -->|"BLOCK_RESPONSE"| S7 --> FINAL
        S3 -->|"REVIEW_QUEUE"| S8 --> OPDATA
    end

    subgraph FINAL_LAYER["Final Response Layer"]
        FINAL["final_answer 생성<br/>QA_ticket.raw_content에<br/>Q/A 형식으로 append"]
    end

    FINAL --> OPDATA

    subgraph OPDATA["Step 5. Operational Data Logging"]
        D1["QA_ticket<br/>raw_content, final_answer, status"]
        D2["ticket_analysis<br/>category, routing_target"]
        D3["answer_draft<br/>draft_id, content"]
        D4["evidence_docs<br/>근거 로그 / 문서"]
        D5["safety_results<br/>decision_type, scores, reason"]
        D6["failed_queries<br/>FAQ/RAG 실패 전용"]
        D7["VOC_DB<br/>VOC 유형 / 키워드"]
        D8["operator_queue<br/>urgent_alert / review_queue"]
    end

    OPDATA --> DASH["Operator Dashboard / Analytics<br/>운영 대시보드에서 분석 및 처리"]
```

## Layer Summary

| Layer | 책임 |
|------|------|
| Access Layer | 사용자 문의 입력, 세션 식별, 입력 payload 생성 |
| Orchestration Layer | 입력 정제, 문의 분류, 라우팅 결정, 티켓/분석 결과 저장 |
| Intelligence Layer | FAQ, Bug, Payment, VOC별 근거 조회 및 답변 초안 생성 |
| Safety Layer | 답변 초안 검증, `decision_type` 저장, 안전성 분기 결정 |
| Final Response Layer | 사용자에게 나갈 최종 답변 생성 및 Q/A 누적 준비 |
| Operational Data Logging | 운영 대시보드가 소비할 데이터 적재 |

## Storage Policy

챗봇은 운영 인사이트를 직접 계산하지 않고, 운영 대시보드가 분석할 수 있는 데이터를 남기는 역할까지만 담당합니다.

```text
QA_ticket
  -> 사용자 문의 원문, 최종 답변, 상태 저장

ticket_analysis
  -> category, routing_target 저장

answer_draft
  -> agent가 생성한 답변 초안 저장

evidence_docs
  -> 답변 근거가 된 로그 또는 문서 저장

safety_results
  -> decision_type, safety score, reason 저장

failed_queries
  -> FAQ/RAG에서 답변 근거를 찾지 못한 질문만 저장

VOC_DB
  -> VOC 유형, 키워드, 원문/정규화 질의 저장

operator_queue
  -> urgent_alert, review_queue 등 운영자 확인 대상 저장
```

## Current Implementation Note

현재 코드의 LangGraph 실험 경로는 아래 흐름까지 구현되어 있습니다.

```text
orchestrator
  -> category agent
     -> VOC이면 final_response
     -> 결제/인게임버그/FAQ이면 safety_layer -> final_response
  -> END
```

현재 구현은 seed/mock tool 기반 baseline입니다. 실제 RAG/ChromaDB 검색과 운영 대시보드 연동은 후속 작업으로 연결합니다. `QA_ticket.raw_content` append는 `append_qa_ticket_message` tool 계약으로 준비되어 있습니다.

## Run

현재 `runners/run_chatbot.py`는 LangGraph `StateGraph` 경로를 실행합니다.

```bash
python3 runners/run_chatbot.py
```

현재 공식 챗봇 실행 runner는 `chatbot.graph.workflow.graph`를 호출합니다.

```text
runners/run_chatbot.py
  -> chatbot.graph.workflow.graph
  -> orchestrator
  -> category agent
  -> VOC이면 final_response
  -> 결제/인게임버그/FAQ이면 safety_layer
  -> final_response
```

주의할 점은 category agent 내부에서 공통 `create_agent` reasoning을 호출할 수 있다는 점입니다. 따라서 graph runtime 검증은 OpenAI API 연결이 가능한 환경에서 실행해야 합니다.
