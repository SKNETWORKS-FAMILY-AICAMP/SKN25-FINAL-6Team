# Chatbot

게임 CS 고객 응대를 담당하는 챗봇 모듈입니다.

현재 챗봇의 메인 구현은 `create_agent` 기반이며, 고객 문의를 받아 필요한 tool을 호출하고 답변을 생성합니다.

## 역할

- 고객 문의 접수
- 문의 카테고리 판단
- 결제/환불/지급/가챠 로그 조회
- FAQ/정책 문서 검색
- 답변 초안 생성
- 티켓 분석, 답변, 근거, safety 결과 저장

## 폴더 구조

```text
chatbot/
├─ agent.py
├─ schemas.py
├─ constants.py
├─ tools/
│  ├─ db_tools.py
│  ├─ vector_tools.py
│  ├─ cache_tools.py
│  └─ README.md
└─ README.md
```

## 주요 파일

| 파일 | 설명 |
|------|------|
| `agent.py` | LangChain `create_agent` 기반 메인 챗봇 agent |
| `schemas.py` | 챗봇 state 스키마 정의 |
| `constants.py` | 카테고리, 라우팅, safety threshold 상수 |
| `tools/db_tools.py` | DB 조회/저장 tool |
| `tools/vector_tools.py` | 문서 embedding/search/rerank tool |
| `tools/cache_tools.py` | FAQ 답변 캐시 tool |

## 실행 흐름

```text
사용자 문의
  -> runners/run_chatbot.py
  -> chatbot.agent.agent
  -> create_agent
  -> 필요한 tool 호출
  -> 답변 생성
```

`create_agent`는 사용자 메시지를 보고 필요한 tool을 선택합니다. 결제 문의면 결제/지급 로그를 조회하고, FAQ성 문의면 문서 검색 또는 캐시를 사용할 수 있습니다.

## State

`schemas.py`의 `ChatbotState`는 agent 실행 중 필요한 상태값을 정의합니다.

주요 값:

| 필드 | 설명 |
|------|------|
| `messages` | LangChain 대화 메시지 |
| `user_id` | 사용자 ID |
| `session_id` | 현재 챗봇 세션 ID |
| `account_id` | 게임 계정 ID |
| `source_type` | 유입 채널 |
| `raw_content` | 사용자 문의 원문 |
| `cleaned_content` | 정제된 문의 내용 |
| `ticket_id` | QA 티켓 ID |
| `category` | 문의 카테고리 |
| `routing_target` | `rag_reply` 또는 `urgent_alert` |
| `draft_id` | 답변 초안 ID |
| `answer_draft` | 답변 초안 |
| `safety_passed` | safety 통과 여부 |
| `retry_count` | 재시도 횟수 |

현재 state 자체는 영구 저장하지 않습니다. DB에 남길 데이터는 tool을 통해 별도로 저장합니다.

## 저장 정책

현재 `USE_SEED_PAYLOAD=true`이면 `db_tools.py`의 write tool은 실제 DB 저장 대신 mock 응답을 반환합니다.

실제 DB 연동 시 저장 대상은 다음과 같습니다.

| 대상 | 내용 |
|------|------|
| `QA_ticket` | 문의 원문 및 Q/A 누적 기록 |
| `ticket_analysis` | 카테고리, 위험도, 감정, 라우팅 결과 |
| `answer_draft` | 생성된 답변 초안 |
| `evidence_docs` | 답변에 사용된 근거 문서/로그 |
| `safety_results` | safety 평가 결과 |

향후 실제 DB 접근 코드는 공통 DB access layer로 분리합니다.

## 실행 방법

프로젝트 루트에서 실행합니다.

```powershell
python runners\run_chatbot.py
```

## 환경 변수

`.env.sample`을 참고합니다.

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
EMBEDDING_MODEL=openai:text-embedding-3-small
RETRIEVAL_TOP_K=3
USE_SEED_PAYLOAD=true
DATABASE_URL=postgresql://...
```

## 현재 한계

- 실제 DB access layer는 아직 구현 전입니다.
- `USE_SEED_PAYLOAD=false`이면 DB-backed tool은 `NotImplementedError`를 발생시킵니다.
- safety 5종 분기, HITL, 운영 대시보드 적재는 별도 구현이 필요합니다.
