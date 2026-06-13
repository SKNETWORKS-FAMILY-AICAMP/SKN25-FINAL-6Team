# 챗봇 리팩토링 인계 문서

이 문서는 `apps/chatbot` 코드를 정리하거나 다른 운영 코드와 연결할 팀원을 위한 챗봇 중심 인계 문서다. 현재 코드 기준으로 실제 파일명, 처리 흐름, 유지해야 하는 설계 의도, 리팩토링 주의점을 정리했다.

## 1. 챗봇의 역할

챗봇은 사용자가 직접 접속해 문의를 남기는 일상 고객센터 화면과 API를 담당한다.

주요 목적은 다음과 같다.

```text
1. 로그인된 사용자/계정 기준으로 qa_ticket에 문의를 접수한다.
2. 사용자가 선택한 카테고리에 따라 payment, bug, faq, voc 흐름으로 분기한다.
3. 자동 답변 가능한 문의는 draft, evidence, safety 결과를 저장하고 resolved 처리한다.
4. 명확히 해결하기 어렵거나 운영자 확인이 필요한 문의는 REVIEW_REQUIRED/pending으로 남긴다.
5. FAQ/RAG 근거 부족은 failed_queries에 남겨 문서 보강 대상으로 추적한다.
6. review_required인 버그성 문의는 GitHub issue 알림 대상으로 처리한다.
```

## 2. 주요 폴더 구조

```text
apps/chatbot/backend
  api/                 FastAPI endpoint
  chains/              LangGraph workflow와 routing
  chatbot/             chatbot.* import를 열어주는 package shim
  evals/               LangSmith/RAGAS 평가 스크립트와 dataset
  generation/          category별 agent와 prompt, 최종 응답 생성
  notifications/       GitHub issue 알림
  observability/       로그, LangSmith metadata, error 분류
  repository/          DB read/write 계층
  retrieval/           FAQ retrieval cache
  safety/              답변 safety/grounding/review 판단
  service/             API에서 호출하는 application service
  tools/               LangChain tool 형태의 read-only DB 조회
  utils/               입력 전처리, 비밀번호 검증, query rewrite
  agent.py             payment/bug LangChain agent builder
  constants.py         retry, category, safety threshold 상수
  schemas.py           ChatbotState와 API 내부 schema

apps/chatbot/frontend/static
  index.html           로그인, 채팅, 문의내역, FAQ UI가 들어 있는 단일 정적 페이지
  assets/              배경/캐릭터/로딩 이미지
```

## 3. Import 구조 주의점

현재 코드는 대부분 다음처럼 import한다.

```python
from chatbot.generation.faq_agent import faq_agent_node
from chatbot.repository.ticket_repository import save_qa_ticket
```

그런데 실제 `generation`, `repository`, `service` 폴더는 `apps/chatbot/backend/chatbot/` 안이 아니라 `apps/chatbot/backend/` 바로 아래에 있다.

이를 맞추기 위해 `apps/chatbot/backend/chatbot/__init__.py`가 `backend` 루트를 `chatbot` 패키지 경로에 추가한다. 따라서 현재 구조에서는 `chatbot/__init__.py`를 삭제하면 안 된다.

장기적으로 깔끔하게 바꾸려면 실제 모듈들을 아래처럼 옮기는 패키지 구조 리팩토링이 필요하다.

```text
apps/chatbot/backend/chatbot/
  api/
  chains/
  generation/
  repository/
  retrieval/
  safety/
  service/
  tools/
  utils/
  constants.py
  schemas.py
```

단, 이 작업은 import, Dockerfile, eval script, 실행 명령을 모두 건드리므로 별도 브랜치에서 해야 한다.

## 4. API 흐름

파일: `apps/chatbot/backend/api/main.py`

주요 endpoint:

```text
GET  /health
GET  /server-regions
POST /login
GET  /tickets
POST /chat
```

`/chat` 처리 흐름:

```text
1. 백엔드에서 새 ticket_id 생성
2. 기존 session_id가 있으면 base는 유지하고 turn 번호 증가
3. 이전 메시지가 request에 없으면 DB에서 같은 세션의 최근 turn 조회
4. service/chatbot_service.py의 run_chatbot 호출
5. answer, ticket_id, session_id, draft_id, category, safety 결과 반환
```

`session_id`는 `883597479-1`, `883597479-2`처럼 같은 상담 base와 turn 번호를 같이 가진다.

## 5. LangGraph Workflow

파일: `apps/chatbot/backend/chains/workflow.py`

등록된 node:

```text
ticket_preprocess
payment_agent
bug_agent
faq_agent
voc_agent
draft_persistence
safety_layer
final_response
```

전체 흐름:

```text
ticket_preprocess
  -> payment_agent | bug_agent | faq_agent | voc_agent | final_response
  -> draft_persistence
  -> safety_layer | final_response
  -> final_response
  -> END
```

중요한 분기:

```text
prompt_injection
  -> agent를 거치지 않고 final_response

voc
  -> 고정 응답 생성 후 safety 생략 가능

payment/bug/faq
  -> draft 저장 후 safety 검사

REVIEW_REQUIRED
  -> final_response에서 qa_ticket.status=pending
```

## 6. 입력 전처리

파일: `apps/chatbot/backend/utils/input_preprocessing.py`

처리 내용:

```text
사용자 입력
  -> 개인정보/민감정보 regex 마스킹
  -> korcen 욕설 감지 후 [PROFANITY] 마스킹
  -> prompt injection 의심 regex 감지 후 [PROMPT_INJECTION] 마스킹
  -> masked_content, input_detected_labels 생성
```

현재 유지할 핵심 값:

```text
raw_query
  사용자 원문

masked_content
  PII 등 마스킹 처리 결과

normalized_query
  맞춤법/공백 등을 정리한 쿼리. RAG 검색/agent 입력에 사용된다.

input_detected_labels
  마스킹 대상으로 감지된 레이블 목록

input_masked
  마스킹이 실제 적용됐는지 여부
```

## 7. Category Routing

파일: `apps/chatbot/backend/chains/routing.py`

기본 category 매핑:

```text
payment -> payment_agent
bug     -> bug_agent
faq     -> faq_agent
voc     -> voc_agent
```

`routing_target` 매핑:

```text
payment_agent -> payment_agent
bug_agent     -> bug_agent
faq_agent     -> faq_agent
voc_agent     -> voc_agent
rag_reply     -> faq_agent
```

`urgent_alert`는 더 이상 routing_target으로 사용하지 않는다. GitHub issue 생성 여부는 `review_required`와 버그성 문의 여부로 판단한다.

프론트에서는 사용자가 고른 subcategory routing을 우선한다. 현재는 문장 키워드로 category를 다시 뒤집는 LLM 라우터를 사용하지 않는다.

## 8. 프론트 2차 카테고리 라우팅

파일: `apps/chatbot/frontend/static/index.html`

버그/오류 카테고리는 세분화되어 있다.

```text
실행/접속 오류              -> bug_agent
게임 진행 오류              -> bug_agent
그래픽/사운드 오류          -> bug_agent
오류 메시지/크래시          -> bug_agent
결제 후 아이템 미지급       -> payment_agent
보상/우편 미수령            -> payment_agent
가챠/뽑기 기록 이상         -> payment_agent
기타 오류 제보              -> bug_agent
```

후속 턴에서 "다 해봤어", "아직 안 돼", "2시간 지났어" 같은 표현을 별도 룰로 라우팅 보정하는 로직은 현재 넣지 않았다.

## 9. Payment Agent

파일: `apps/chatbot/backend/generation/payment_agent.py`

payment agent는 로그인된 `user_id/account_id` 기준으로 결제 관련 DB context를 먼저 모은다.

조회 대상:

```text
accounts
payments
refunds
item_delivery_logs
gacha_logs
```

처리 방식:

```text
collect_payment_context_by_user()
  -> payment_context 생성
  -> item_delivery_logs를 relevant/other로 분리
  -> LLM system message에 JSON context로 추가
  -> retrieved_documents 형태의 evidence로 변환
  -> safety_layer가 같은 DB 근거로 grounding/review 판단
```

아이템 지급 로그 매칭:

```text
relevant_item_delivery_logs
  사용자 문의의 아이템명/보상명/상자명과 명확히 맞는 지급 로그

other_item_delivery_logs
  같은 계정의 최근 지급 로그지만 문의 대상과 일치한다고 단정하면 안 되는 로그
```

예를 들어 사용자가 `보스 보상 상자`를 물었는데 DB에 `스타터 패키지 상자`만 있으면 `relevant_item_delivery_logs`는 비어 있고, `스타터 패키지 상자`는 `other_item_delivery_logs`로 분리된다.

주의:

- payment node는 repository를 직접 호출한다.
- `tools/db_tools.py`에도 payment context tool이 남아 있지만, 현재 핵심 흐름은 node에서 먼저 context를 수집하는 구조다.
- 결제 성공인데 아이템 지급 기록이 없거나 환불 진행 상태가 있으면 `REVIEW_REQUIRED`/pending 대상이 될 수 있다.
- 특정 아이템명/보상명/상자명이 언급된 경우, 일치하는 로그가 없으면 다른 아이템 기록을 문의 대상처럼 단정하지 않아야 한다.

## 10. Bug Agent

파일: `apps/chatbot/backend/generation/bug_agent.py`

bug agent는 LangChain `create_agent` 기반이며 tool calling이 가능하다.

연결된 tool:

```text
read_item_delivery_logs(account_id)
read_gacha_logs(account_id)
```

다만 결제/아이템 미지급/가챠 기록 이상처럼 결제성 DB context가 중요한 문의는 프론트 2차 카테고리에서 처음부터 `payment_agent`로 보내는 것이 현재 설계다.

`bug_agent`로 들어간 문의가 `review_required=True` 또는 `safety_action=REVIEW_REQUIRED`가 되면 GitHub issue 생성 대상이 될 수 있다.

## 11. FAQ/RAG Agent

파일: `apps/chatbot/backend/generation/faq_agent.py`

FAQ는 LangChain `create_agent`가 아니라 직접 RAG pipeline을 실행한다.

흐름:

```text
active query 추출
-> normalized/retrieval query 생성
-> retrieval cache lookup
-> embedding 생성
-> hybrid search
-> rerank
-> relevance gate
-> 필요 시 query rewrite 후 재검색
-> evidence 기반 답변 생성
```

FAQ 실패 시 `failed_queries`에 저장한다.

대표 reason:

```text
rag_not_requested
low_information_complaint
empty_retrieval_query
no_retrieved_documents
empty_retrieved_documents
low_retrieval_score:<score>
retrieval_relevance_gate_failed
safety_safe_fallback
```

`safety_safe_fallback`은 FAQ/RAG 답변이 생성됐지만 safety 단계에서 `SAFE_FALLBACK`으로 바뀐 경우 final_response 단계에서 저장된다.

## 12. Retrieval Cache

파일: `apps/chatbot/backend/retrieval/cache_store.py`

현재 cache는 최종 답변 cache가 아니라 FAQ retrieval 결과 cache다.

```text
retrieval_query hash
  -> Redis 또는 memory cache 조회
  -> hit이면 cached documents 사용
  -> answer generation은 다시 수행
```

따라서 `retrieval_cache_hit=true`는 "최종 답변을 그대로 재사용했다"는 뜻이 아니다.

## 13. Safety Layer

파일: `apps/chatbot/backend/safety/safety_layer.py`

역할:

```text
답변 개인정보/민감정보 마스킹
DB 문서에 있는 공식 연락처/URL 마스킹 예외 처리
FAQ/RAG evidence grounding 검사
moderation/rule 기반 safety 판단
운영자 확인 필요 여부 판단
safety_results 저장
```

주요 action:

```text
AUTO_RESPONSE
MASKING
SAFE_FALLBACK
BLOCK_RESPONSE
REVIEW_REQUIRED
```

상태 의미:

```text
AUTO_RESPONSE
  자동 응답 가능

MASKING
  답변에 민감정보가 남아 있어 마스킹 또는 재처리 필요

SAFE_FALLBACK
  근거 부족/grounding 실패 등으로 안전한 fallback 사용

BLOCK_RESPONSE
  공격성, prompt injection, 정책 위반 등 자동 답변 제공 부적절

REVIEW_REQUIRED
  답변은 가능하지만 운영자 개입이 필요한 문의
```

## 14. Final Response

파일:

```text
apps/chatbot/backend/generation/response/final_response.py
apps/chatbot/backend/generation/response/fixed_responses.py
```

역할:

```text
safety_action에 따라 최종 답변 결정
review_required인 버그성 문의면 GitHub issue 생성
FAQ SAFE_FALLBACK이면 failed_queries 저장
qa_ticket.raw_query와 status 업데이트
```

status 기준:

```text
REVIEW_REQUIRED 또는 review_required=True -> pending
그 외 -> resolved
```

현재 문의 내역 표시를 위해 `qa_ticket.raw_query`를 다음 형태로 갱신한다.

```text
User: {raw_query}
AI: {final_text}
```

장기적으로는 `qa_ticket.raw_query`는 사용자 원문만 저장하고 최종 답변은 `final_response` 테이블에 저장하는 구조가 더 깔끔하다. 다만 현재 프론트 문의 내역은 이 User/AI 포맷에 의존한다.

## 15. GitHub Issue Notification

파일:

```text
apps/chatbot/backend/notifications/github_issue.py
apps/chatbot/backend/repository/notification_repository.py
```

현재 챗봇 알림은 GitHub issue 중심이다.

흐름:

```text
final_response
  -> dispatch_github_issue_notification()
  -> review_required인 버그성 문의가 아니면 skipped
  -> 대상이면 GitHub issue 생성
  -> notification_logs에 결과 저장
```

생성 조건:

```text
(review_required=True 또는 safety_action=REVIEW_REQUIRED)
AND
(category=bug 또는 reasoning_node=bug_agent)
```

환경변수:

```text
GITHUB_TOKEN
GITHUB_REPOSITORY
GITHUB_ISSUE_LABELS
```

토큰이나 repository가 없으면 실제 issue를 만들지 않고 mock 결과를 반환한다.

## 16. DB 저장 흐름

```text
ticket_preprocess
  -> qa_ticket 최초 저장

category agent
  -> draft_text 생성

draft_persistence
  -> answer_draft 저장
  -> evidence_docs 저장

safety_layer
  -> safety_results 저장

final_response
  -> qa_ticket.raw_query User/AI 형태로 갱신
  -> qa_ticket.safety_action 갱신
  -> qa_ticket.status 갱신
  -> 필요 시 failed_queries 저장
  -> 필요 시 notification_logs 저장
```

## 17. Evals

현재 실제로 남아 있는 주요 eval 파일:

```text
apps/chatbot/backend/evals/audit_db_grounded_dataset.py
apps/chatbot/backend/evals/run_langsmith_regression_eval.py
apps/chatbot/backend/evals/upload_langsmith_dataset.py
```

주의:

- 현재 파일 목록에 없는 eval script 이름을 문서나 실행 가이드에 남기지 말 것.
- RAGAS/LangSmith 평가는 `run_langsmith_regression_eval.py` 기준으로 확인할 것.

## 18. Docker 배포

backend Dockerfile:

```text
apps/chatbot/backend/Dockerfile
```

frontend nginx Dockerfile:

```text
deploy/nginx/Dockerfile
deploy/nginx/default.conf
```

WSL/Windows에서 `.pytest_cache` xattr 문제로 build가 실패하면 tar 방식으로 build context를 넘긴다.

```bash
tar \
  --exclude=.pytest_cache \
  --exclude='*/.pytest_cache' \
  --exclude=.venv \
  --exclude=.git \
  -cf - . | docker build -t chatbot-backend -f apps/chatbot/backend/Dockerfile -
```

접속 URL:

```text
http://localhost:8080/chatbot/
```

Docker `--env-file .env`에서는 다음처럼 공백과 따옴표를 피해야 한다.

```text
DB_PORT=5432
```

`DB_PORT = "5432"`처럼 쓰면 컨테이너 안에서 `int('"5432"')` 에러가 난다.

## 19. 리팩토링 우선순위

파일 수를 늘리지 않는 방향으로 줄이고 싶다면 다음 순서가 현실적이다.

```text
1. generation/policies.py 축소 또는 제거 검토
2. tools/db_tools.py에서 실제 미사용 tool 제거
3. notification 관련 이름/주석 정리 유지
4. 빈 __init__.py 일부 삭제 검토
5. final_response 테이블 사용 여부 정리
```

주의:

- `chatbot/__init__.py`는 현재 import 구조에서 필요하다.
- `faq_agent.py`와 `safety_layer.py`는 크지만 억지로 합치면 더 복잡해진다.
- `frontend/static/index.html`은 크지만 단일 정적 배포라 지금 구조에서는 동작이 단순하다.

## 20. 병합 리팩토링 시 핵심 주의점

1. 챗봇은 사용자-facing 자동 응답 시스템이다.
2. 명쾌히 해결하지 못하는 문의는 `REVIEW_REQUIRED`와 `qa_ticket.status=pending`으로 남겨야 한다.
3. payment 답변은 반드시 로그인된 사용자 범위 DB context를 기준으로 해야 한다.
4. 특정 아이템/보상/상자 문의는 일치하는 지급 로그만 근거로 사용해야 한다.
5. FAQ 답변은 retrieved evidence 기반이어야 하며, 근거 부족은 `failed_queries`로 남겨야 한다.
6. `qa_ticket.raw_query`에 User/AI를 합쳐 저장하는 현재 방식은 프론트 문의 내역과 연결되어 있으므로, 변경 시 프론트도 같이 고쳐야 한다.
7. GitHub issue 알림은 `notifications/github_issue.py` 기준으로 보면 된다.

## 21. Pending 처리 조건

`final_response` 단계에서 최종 티켓 상태를 결정한다.

다음 조건 중 하나라도 해당하면 `qa_ticket.status`는 `pending`으로 남는다.

```text
safety_action == "REVIEW_REQUIRED"
review_required == true
```

현재 `REVIEW_REQUIRED` 또는 `review_required=true`가 될 수 있는 대표 케이스는 다음과 같다.

```text
- 환불 상태가 진행 중인 결제 문의
  - refund_status가 requested, pending, reviewing, in_progress, processing인 경우

- 결제는 성공했지만 아이템 지급 확인이 필요한 문의
  - 사용자가 지급/미지급/아이템/보상 관련 문의를 했고
  - payment_status가 성공/완료/paid 계열이며
  - 지급 로그가 없거나 delivery_status가 pending, failed, processing, requested 등인 경우

- 답변 또는 문의 내용에 운영자 검토가 필요한 표현이 포함된 경우
  - 담당자 확인/검토/처리/안내
  - 운영자 확인/검토/처리/안내
  - 티켓 검토/접수/처리
  - 별도 안내
  - 수동 지급/보상/환불/복구/처리
  - 환불/결제 취소 승인/검토/진행 중
  - 계정 복구/제재 해제/연동 해제 요청 또는 검토
  - 로그/재현/증빙/영수증 확인 필요
  - 자동 처리 또는 AI 판단이 어렵다는 내용
```

그 외 자동 응답 가능한 케이스는 보통 `resolved`로 종료된다.
