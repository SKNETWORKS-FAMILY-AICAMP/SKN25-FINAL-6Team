# Chatbot Folder Structure

전체 프로젝트 안에서 챗봇 관련 코드는 `chatbot/`에 두고,
챗봇 전용 문서와 테스트는 루트 공용 폴더 아래 `chatbot/` 하위 폴더로 모읍니다.

```text
SKN25-FINAL-6Team/
├── docs/
│   └── chatbot/              # 챗봇 전용 설계/운영 문서
├── tests/
│   └── chatbot/              # 챗봇 전용 테스트
├── runners/
│   ├── run_chatbot.py        # 챗봇 CLI 실행
│   └── streamlit_chatbot.py  # 챗봇 Streamlit 실행
└── chatbot/
    ├── agent.py              # create_agent 생성 진입점
    ├── schemas.py            # ChatbotState, Pydantic 계약
    ├── constants.py          # 공통 상수
    ├── generation/prompts/              # 시스템/노드별 프롬프트
    ├── chains/                # StateGraph workflow와 routing
    ├── generation/               # orchestrator, payment/faq/bug/voc nodes, drafting helper
    ├── retrieval/            # cache/vector/embedding/retriever wrapper
    ├── repository/         # DB 저장/조회 책임 분리 예정 영역
    ├── tools/                # LangChain tool wrapper와 registry
    ├── safety/               # safety layer와 향후 moderation/PII 검사
    ├── generation/response/             # final response와 고정 응답 문구
    ├── memory/               # session_id 기반 멀티턴 이력 확장 영역
    ├── notifications/        # Slack 등 urgent alert 알림
    ├── observability/        # 관리자 로그/event 구조
    └── utils/                # config/error 등 공통 유틸
```

## Current Notes

```text
agent.py
  -> payment/faq/bug policy가 넘긴 prompt/tools로 create_agent 생성

chains/workflow.py
  -> StateGraph 구성
  -> chains/routing.py의 route 함수를 사용

generation/drafting_agent.py
  -> concrete agent 실행 결과를 StateGraph update로 변환

repository/
  -> 현재는 db_tools wrapper를 re-export하는 단계
  -> 실제 DB 연결 시 repository 내부 구현을 채우면 됨

retrieval/
  -> 현재는 cache_tools/vector_tools wrapper
  -> ChromaDB 연결 시 vector_store/retriever 쪽에서 확장

runners/streamlit_chatbot.py
  -> Streamlit 실행 진입점
  -> streamlit run runners/streamlit_chatbot.py
```
