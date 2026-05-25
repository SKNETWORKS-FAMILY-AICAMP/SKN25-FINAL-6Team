# 데이터 생성 계획

## 1. 범위

이 문서는 아래 테이블에 대한 데이터 생성 계획만 다룬다.

- `community_users`
- `game_accounts`
- `qa_ticket`
- `payments`
- `refunds`
- `item_delivery_logs`
- `gacha_logs`

이번 계획에서 제외하는 항목:

- `ticket_analysis`
- `insight`
- `voc_feedback`
- `documents`
- `documents_chunks`
- `documents_embeddings`
- `answer_draft`
- `evidence_docs`
- `safety_results`
- `final_response`
- `notification_logs`
- `failed_queries`
- `admin_event_logs`

`documents` 계열은 수정하지 않는다.

## 2. DB 문서 기준 사실

아래 내용은 `docs/DB/descriptions.md`, `docs/DB/notion_data.md`, `docs/DB/db_info.md`를 기준으로 확정된 사실로 본다.

- `qa_ticket`는 live DB 기준 약 9,243건이다.
- `community_users`와 `game_accounts`는 각각 약 6,288건이다.
- `qa_ticket`는 `ticket_id`, `account_id`, `user_id`, `title`, `raw_query`, `source_type`, `status`, `inquiry_created_at`, `session_id`, `responder_type`를 가진다.
- `qa_ticket.account_id`는 nullable이고 `game_accounts.account_id`를 참조한다.
- `qa_ticket.user_id`는 필수이며 `community_users.user_id`를 참조한다.
- 적재 노트북은 `qa_ticket`의 non-null `account_id`와 `user_id` 매핑으로 `game_accounts`를 만든다.
- 현재 스키마에는 별도 챗봇 대화 로그 테이블이 없다.
- 따라서 챗봇 문의 흐름은 `qa_ticket.source_type`, `session_id`, `responder_type`로만 간접 표현된다.
- `source_type`, `status`, `responder_type`, 문의 길이, 재문의 여부는 원천 분포를 그대로 복제하는 대상이 아니라 AI가 판정하거나 부여할 수 있는 속성으로 본다.

이 사실 때문에 생성 전략은 아래처럼 갈라져야 한다.

- 게임 유저 이용 관련 데이터: `community_users`, `game_accounts`, `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`
- 문의 데이터: `qa_ticket`
- 운영 메타 속성: `source_type`, `status`, `responder_type`, 길이, 재문의 여부는 생성 후 AI가 판정/부여

## 3. 계획 수립 근거

이 계획은 아래 문서를 기준으로 작성한다.

- [descriptions.md](/C:/final_project/data_gen/docs/DB/descriptions.md:42)
- [descriptions.md](/C:/final_project/data_gen/docs/DB/descriptions.md:66)
- [descriptions.md](/C:/final_project/data_gen/docs/DB/descriptions.md:122)
- [notion_data.md](/C:/final_project/data_gen/docs/DB/notion_data.md:281)
- [notion_data.md](/C:/final_project/data_gen/docs/DB/notion_data.md:303)
- [paper_description.md](/C:/final_project/data_gen/paper_description.md:137)
- [paper_description.md](/C:/final_project/data_gen/paper_description.md:413)
- [paper_description.md](/C:/final_project/data_gen/paper_description.md:577)

논문 기반 핵심 원칙은 다음과 같다.

- 실제 문의 데이터를 seed로 우선 사용한다.
- 부족한 케이스만 합성 데이터로 보강한다.
- 중복 제거, 정책 필터링, 샘플 운영자 검수를 거친다.
- 문의의 의미와 말투는 유지하되 개인정보 및 재식별 위험은 줄인다.
- 단순 생성 품질이 아니라 실제 분류, 라우팅, 응대 품질에 도움이 되는지로 평가한다.
- 희귀 케이스와 고위험 케이스는 평균 분포에 묻히지 않게 별도 quota를 둔다.

## 4. 전체 방향

데이터 생성 순서는 아래와 같이 잡는다.

1. 게임 유저 이용 관련 데이터의 구조와 시나리오를 먼저 만든다.
2. `community_users`, `game_accounts`를 생성한다.
3. `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`를 유저 이용 흐름에 맞춰 생성한다.
4. 그 이용 이력에 맞는 `qa_ticket`를 생성하거나 정제한다.
5. 생성된 `qa_ticket`에 대해 `source_type`, `status`, `responder_type`, 길이, 재문의 여부를 AI가 판정/부여한다.
6. 최종적으로 FK, 시점, 시나리오 정합성을 검수한다.

이 순서를 권장하는 이유는 이번 작업의 본체가 "문의 분포 복제"가 아니라 "게임 이용 맥락이 살아 있는 유저 데이터와 그에 맞는 문의 생성"이기 때문이다.

## 5. 생성 범위 재정의

이번 작업에서 직접 생성하는 본체는 두 축이다.

- 게임 유저 이용 관련 데이터
  - `community_users`
  - `game_accounts`
  - `payments`
  - `refunds`
  - `item_delivery_logs`
  - `gacha_logs`
- 문의 데이터
  - `qa_ticket`

아래 속성은 생성 목표라기보다 후처리 라벨 또는 AI 판정 영역으로 둔다.

- `source_type`
- `status`
- `responder_type`
- 문의 길이 버킷
- 재문의 여부
- 감정 강도
- 카테고리 보조 라벨

즉 이번 문서의 핵심은 "분포를 미리 맞추는 것"보다 "유저 이용 이력과 문의 내용이 서로 설명되도록 만드는 것"이다.

## 5.1 생성 목표 수량

`paper_description.md` 기준으로 이번 생성은 대량 합성이 아니라 `실제 분포를 기준으로 한 제한적 보강`으로 잡는다. 따라서 `qa_ticket`은 live DB 규모(9,243건)에 가깝게 두고, 부족한 hard case와 high-risk 케이스만 별도 quota로 보강한다. `community_users`, `game_accounts`도 live 기준치(각 6,288건)를 크게 벗어나지 않게 맞춘다.

| 테이블 | 목표 수량 | 기준 |
| --- | ---: | --- |
| `community_users` | 630 | live 기준 6,288건의 1/10 축소 target. `qa_ticket.user_id`를 안정적으로 수용할 최소 모수 |
| `game_accounts` | 630 | live 기준 6,288건의 1/10 축소 target. 기본은 1유저 1계정, 일부 hard case만 예외 |
| `qa_ticket` | 950 | live 기준 9,243건의 1/10 축소 target + 부족한 hard case 약 26건 보강 |
| `payments` | 320 | 전체 계정의 부분집합. 결제/환불/미지급 문의를 설명할 수 있는 수준으로만 생성 |
| `refunds` | 55 | `payments`의 부분집합. 정상 환불, 지연, 분쟁, 거절 케이스 포함 |
| `item_delivery_logs` | 140 | 아이템 미지급, 지급 지연, 이벤트 보상 누락 케이스를 설명할 수 있는 수준 |
| `gacha_logs` | 180 | 가챠 불만, 천장, 배너 오인, 확률 체감 불일치 케이스 포함 |

수량 결정 원칙:

- `qa_ticket`이 본체이고 나머지 테이블은 문의를 설명하는 운영 근거 데이터다.
- `qa_ticket`은 live 규모를 크게 넘기지 않는다. 보강량은 전체의 약 10% 이내로 제한한다.
- `payments`, `refunds`, `item_delivery_logs`, `gacha_logs`는 실제 운영 비율 복제가 목적이 아니라 `문의 설명 가능성` 확보가 목적이다.
- 평균적인 문의만 늘리지 않고 `repeated complaint`, `urgent`, `legal threat`, `security`, `sanction dispute` 같은 hard case를 별도 quota로 포함한다.

권장 보강 quota:

- `qa_ticket` 추가 보강 26건 중 최소 18건은 hard case로 배정한다.
- hard case 내부 권장 배분: `refund/legal` 4, `security/account takeover` 4, `sanction dispute` 2, `payment success but item missing` 3, `event reward missing` 2, `chatbot failure/escalation` 3.
- 나머지 약 8건은 일반 분포의 빈약한 꼬리 구간을 메우는 용도로 사용한다.

## 6. 테이블별 생성 계획

### 6.1 `community_users`

목적:

- 실제 사용자를 복원하지 않는 완전 합성 사용자 프로필 생성
- 문의와 연결될 수 있는 최소한의 계정 주체 정보 제공

생성 원칙:

- `user_id`: 생성기가 관리하는 고유 정수 ID 사용
- `email`: 전부 합성 이메일 사용
- `nickname`: 실닉네임이 아니라 가명 사용
- `created_at`: `qa_ticket.inquiry_created_at`보다 충분히 이전 시점이 되도록 생성
- `user_status`: 코드북 고정값 사용
- `last_login_at`: `user_status` 및 문의 발생 시점과 느슨하게 일관되게 생성
- `password_hash`: 실제 해시가 아니라 더미 형식값 사용
- `password_updated_at`: 가입 시점과 최근 로그인 시점 사이에서 생성

설계 원칙:

- 사용자 프로필은 실문의를 보고 복원하지 않는다.
- 대신 게임 이용 흐름과 느슨한 상관을 둔다.
  - `vip` 또는 최근 로그인 활발 유저는 결제/가챠 이력이 많다.
  - `restricted` 유저는 제재/보안 문의 가능성이 있다.
  - `dormant` 유저는 로그인/복귀 이슈 가능성이 있다.

### 6.2 `game_accounts`

목적:

- 유저의 게임 내 상태를 표현해 문의 맥락을 현실적으로 만든다.

생성 원칙:

- `account_id`: 고유 정수 ID 사용
- `user_id`: `community_users.user_id` FK 사용
- `game_name`: 프로젝트 대상 게임명 또는 소수의 통제된 값 사용
- `uid`: 합성 UID 사용
- `server_region`: 통제된 값 사용
- `progression_level`: 균등분포가 아니라 현실적인 치우친 분포 사용
- `account_status`: 코드북 값 사용
- `created_at`: 유저 생성 시점보다 뒤, 문의 시점보다 앞

설계 원칙:

- 기본은 1유저 1계정이다.
- 실문의에서 다계정이 명시되는 경우에만 일부 다계정을 둔다.
- `qa_ticket.account_id` nullable 특성을 반영해 일부 문의는 계정 미연결 상태로 남긴다.

### 6.3 `qa_ticket`

목적:

- 게임 이용 이력으로 설명 가능한 문의 데이터 생성
- 일부 실제 문의 seed가 있다면 정제 후 사용하고, 부족분은 이용 시나리오 기반으로 생성

생성 원칙:

- `ticket_id`: 고유 정수 ID 사용
- `account_id`: 문의가 계정과 연결되는 경우 FK 사용, 비로그인성 문의는 null 허용
- `user_id`: 필수 FK
- `title`: 실데이터에 있으면 유지, 없으면 `raw_query` 기반으로 짧게 생성
- `raw_query`: 실제 문의 정제본 또는 이용 이력 기반 생성문
- `source_type`: 생성 후 AI 판정 또는 규칙 부여
- `status`: 생성 후 AI 판정 또는 규칙 부여
- `inquiry_created_at`: 이용 이력 직후의 자연스러운 시점으로 생성
- `session_id`: 같은 이슈 반복 또는 이관 맥락이 있을 때만 생성
- `responder_type`: 생성 후 AI 판정 또는 규칙 부여

우선순위:

- 1순위: 실제 문의 seed 정제본
- 2순위: 게임 이용 이력으로 직접 설명 가능한 문의 생성
- 3순위: 롱테일 및 hard case 보강

사전 확정 코드북 예시:

- 문의 카테고리
  - `payment`
  - `refund`
  - `item_missing`
  - `account`
  - `bug`
  - `event`
  - `sanction`
  - `security`
  - `gacha`
- `source_type`
  - `chatbot`
  - `web`
  - `email`
  - `community`
  - `in_game`
- `status`
  - `open`
  - `pending`
  - `resolved`
  - `escalated`
  - `closed`
- `responder_type`
  - `bot`
  - `human`
  - `hybrid`
  - `AI`

주의:

- DB 예시에는 `status='pending'`, `responder_type='AI'`가 등장한다.
- 따라서 허용값 목록은 실제 DB 예시와 운영 흐름을 보고 정하되, 생성 단계에서 미리 분포를 고정할 필요는 없다.

텍스트 제약:

- 문의는 이용 이력의 원인과 요청사항을 분명히 드러내야 한다.
- 지나치게 FAQ형으로 정리하지 않는다.
- 불만 표현, 확인 요구, 보상 요구, 환불 요구 같은 실제 화행을 유지한다.
- 길이와 재문의 여부는 생성 후 AI가 판정 가능한 수준으로 자연스럽게 쓴다.

반드시 포함할 hard case:

- 결제 완료 후 아이템 미지급
- 같은 이슈 재문의
- 챗봇 응답 실패 후 사람 상담 이관
- 제재 이의제기
- 가챠 확률/천장 오해
- 이벤트 보상 누락
- 점검/장애 직후 급증 문의
- 환불 강경 요구 또는 법적 표현이 포함된 문의

### 6.4 `payments`

목적:

- 결제 관련 문의에 대한 운영 근거 데이터 제공

생성 원칙:

- `payment_id`: 고유 정수 ID 사용
- `account_id`: `game_accounts.account_id` FK 사용
- `product_name`: 통제된 상품 목록 사용
- `product_type`: 코드북 값 사용
- `amount`: 실제 상점 가격대 반영
- `currency`: 통제된 소수 값 사용
- `payment_method`: 코드북 값 사용
- `payment_status`: 코드북 값 사용
- `transaction_id`: 합성 거래 ID 사용
- `paid_at`: 문의 시점보다 앞

설계 원칙:

- `payment` 또는 `refund` 또는 `item_missing` 문의가 있는 계정 중심으로 생성한다.
- 모든 계정에 균일 생성하지 않는다.
- 문의 강도와 상태에 따라 실패/지연/중복결제 의심을 의도적으로 포함한다.

### 6.5 `refunds`

목적:

- 환불 요청 및 처리 상황을 표현하는 보조 데이터 생성

생성 원칙:

- `refund_id`: 고유 정수 ID 사용
- `payment_id`: `payments.payment_id` FK 사용
- `refund_status`: 코드북 값 사용
- `refund_reason`: 템플릿형 또는 짧은 서술형
- `requested_at`: `paid_at` 이후
- `processed_at`: 처리 전이면 null 허용

설계 원칙:

- `refunds`는 `payments`의 부분집합으로만 만든다.
- 환불 문의가 있는 케이스 위주로 생성한다.
- 정상 환불과 분쟁성 환불을 모두 넣는다.

### 6.6 `item_delivery_logs`

목적:

- 아이템 지급, 보상 지급, 보상 누락 관련 문의를 설명할 수 있는 근거 데이터 생성

생성 원칙:

- `delivery_id`: 고유 정수 ID 사용
- `payment_id`: 구매성 지급이면 FK 사용, 아니면 null 허용
- `account_id`: `game_accounts.account_id` FK 사용
- `source_type`: 코드북 값 사용
- `item_name`: 통제된 아이템 목록 사용
- `quantity`: 현실적인 정수 범위 사용
- `delivery_status`: 코드북 값 사용
- `expected_at`: 필요 시 생성
- `delivered_at`: 완료 전이면 null 허용

설계 원칙:

- `item_missing` 및 `event` 문의와 강하게 연결한다.
- 지급 지연, 로그상 지급 완료, 실제 체감 미수령 같은 충돌 케이스를 포함한다.

### 6.7 `gacha_logs`

목적:

- 가챠 관련 문의의 근거 데이터를 만든다.

생성 원칙:

- `gacha_id`: 고유 정수 ID 사용
- `account_id`: `game_accounts.account_id` FK 사용
- `banner_name`: 통제된 배너 목록 사용
- `item_name`: 통제된 보상 풀 사용
- `item_type`: 코드북 값 사용
- `rarity`: 통제된 희귀도 값 사용
- `pity_count`: 누적 뽑기 맥락에 맞는 정수값 사용
- `pulled_at`: 문의 시점보다 앞

설계 원칙:

- `gacha` 문의 계정 일부에만 생성한다.
- 천장 오해, 픽업 기대 불일치, 많은 횟수 후 불만을 반드시 포함한다.

## 7. 데이터 생성 절차

### 7.1 코드북 및 AI 판정 기준 확정

생성 전에 아래 값을 실제 DB 허용값 기준으로 확정한다.

- 문의 카테고리
- `source_type`
- `status`
- `responder_type`
- `user_status`
- `account_status`
- 상품 목록
- 아이템 목록
- 결제/환불/지급/가챠 관련 상태값

이 중 `source_type`, `status`, `responder_type`, 길이, 재문의 여부는 "생성 입력"이 아니라 "생성 후 판정 대상"으로 둔다.

### 7.2 실제 문의 seed 정리

입력 소스:

- 팀이 보유한 실제 `qa_ticket` 또는 게시글 문의 원문

처리 순서:

1. 직접 식별자 제거
2. 반복 문의 추적이 필요하면 안정적 가명 치환
3. 깨진 텍스트만 최소 수정
4. 감정 강도와 말투 보존
5. 완전 중복 제거
6. 이용 이력과 연결 가능한 seed 표시

### 7.3 게임 이용 데이터 생성

먼저 아래 흐름을 만든다.

- 사용자 생성
- 계정 생성
- 결제 생성
- 환불 생성
- 아이템 지급/누락 생성
- 가챠 이용 생성

권장 방식:

1. 정상 이용 흐름 생성
2. 문제 상황 삽입
3. 문의 유발 가능 이벤트 표시
4. 시점 정합성 검수

### 7.4 `qa_ticket` 생성

`qa_ticket`는 아래 두 소스를 조합해 만든다.

- 실제 문의 seed 정제본
- 게임 이용 이력 기반 합성 문의

권장 방식:

1. 결제/환불/미지급/가챠/계정/버그 이벤트에서 문의 후보 생성
2. 실제 문의 seed가 있으면 우선 재사용 또는 재서술
3. 이용 이력으로 설명되지 않는 문의는 제거 또는 재설계
4. hard case를 소량 추가

### 7.5 AI 라벨 부여

생성된 `qa_ticket`에 대해 AI 또는 규칙 기반 후처리로 아래 값을 부여한다.

- `source_type`
- `status`
- `responder_type`
- 길이 버킷
- 재문의 여부
- 감정 라벨
- 카테고리 라벨

### 7.6 운영 근거 데이터 생성 검증

문의 시나리오와 운영 데이터의 연결을 다시 검증한다.

- 결제 문의 -> `payments`
- 환불 문의 -> `payments` + `refunds`
- 아이템 미지급 문의 -> `payments` + `item_delivery_logs`
- 이벤트/보상 문의 -> `item_delivery_logs`
- 가챠 불만 문의 -> `gacha_logs`

독립 랜덤 생성보다 이 방식이 문의와 근거 데이터의 정합성이 높다.

## 8. 품질 관리 기준

최소 점검 항목:

- `qa_ticket.raw_query`에 직접 개인정보가 남아 있지 않은가
- 완전 중복 또는 거의 동일한 문의가 과도하게 남아 있지 않은가
- AI가 부여한 분류값이 실제 코드북 안에 있는가
- FK 정합성이 맞는가
  - `qa_ticket.user_id` 존재
  - null이 아닌 `qa_ticket.account_id` 존재
  - 운영 테이블의 `account_id`, `payment_id`가 유효함
- 시점 정합성이 맞는가
  - 유저 생성 <= 계정 생성 <= 운영 이벤트 <= 문의 시점
- 문의 내용이 실제 이용 이력으로 설명 가능한가

논문 기준 점검 항목:

- 의미 보존: 문의 원인과 요구사항이 유지되는가
- 스타일 보존: 화남, 반복, 장문/단문 특성이 유지되는가
- 다양성: 일반 문의, 반복 문의, 긴급 문의가 모두 있는가
- 개인정보 보호: 재식별 위험이 낮은가
- 활용성: 분류, 라우팅, 응대 평가에 실제 도움이 되는가

## 9. 생성 스펙 표

### 9.1 테이블 단위 생성 스펙

| 테이블 | 생성 방식 | 목표 수량 | 주 소스 | 핵심 규칙 | 비고 |
| --- | --- | ---: | --- | --- | --- |
| `community_users` | 완전 합성 | 630 | 없음 | 실사용자 복원 금지, 문의 분포와 느슨한 상관만 허용 | 개인정보 보호 우선 |
| `game_accounts` | 합성 | 630 | `community_users` | 유저와 FK 연결, 문의 이전 시점 생성 | 기본 1유저 1계정 |
| `qa_ticket` | 실데이터 우선 + 시나리오 합성 | 950 | 실제 문의, 게임 이용 이력 | 이용 이력으로 설명 가능해야 함, 운영 메타값은 AI 후처리 | 핵심 테이블 |
| `payments` | 시나리오 기반 합성 | 320 | `qa_ticket`, `game_accounts` | 결제 문의와 정합되게 생성 | 전 유저 대상 아님 |
| `refunds` | 부분집합 합성 | 55 | `payments` | 환불 문의 있는 결제에만 생성 | `payments` 종속 |
| `item_delivery_logs` | 시나리오 기반 합성 | 140 | `qa_ticket`, `payments`, `game_accounts` | 지급/누락/지연 케이스 반영 | 구매/보상 모두 포함 |
| `gacha_logs` | 시나리오 기반 합성 | 180 | `qa_ticket`, `game_accounts` | 가챠 이용 계정 일부에만 생성 | 천장/확률 불만 반영 |

### 9.2 `qa_ticket` 컬럼 생성 스펙

| 컬럼 | 생성 방식 | 규칙 |
| --- | --- | --- |
| `ticket_id` | 생성 | 고유 정수 ID |
| `account_id` | 연결/선택 | 계정 기반 문의면 연결, 아니면 null 허용 |
| `user_id` | 연결 | 반드시 생성된 유저와 연결 |
| `title` | 유지/요약 | 실데이터 제목 우선, 없으면 `raw_query` 요약 |
| `raw_query` | 실데이터 또는 생성 | 실제 문의 정제본 또는 이용 이력 기반 생성 |
| `source_type` | AI 판정/규칙 부여 | 생성 후 부여 |
| `status` | AI 판정/규칙 부여 | 생성 후 부여 |
| `inquiry_created_at` | 유지/보정 | 실데이터 시계열 또는 시나리오 시점 반영 |
| `session_id` | 유지/생성 | 재문의와 이관 맥락이 있을 때만 부여 |
| `responder_type` | AI 판정/규칙 부여 | 생성 후 부여 |

### 9.3 개인정보 처리 스펙

| 항목 | 처리 방식 | 비고 |
| --- | --- | --- |
| 이메일 | 제거 또는 합성값 치환 | 직접 식별자 |
| 닉네임 | 가명 치환 | 반복 문의 추적이 필요하면 안정적 치환 |
| UID | 치환 | 게임 계정 식별자 |
| 주문번호/거래번호 | 치환 | 원문 그대로 남기지 않음 |
| 전화번호 | 제거 | 직접 식별자 |
| 소셜 계정 | 제거 또는 치환 | 디스코드, SNS 등 |
| 길드/클랜명 | 필요 시 치환 | 재식별 위험 완화 |

### 9.4 생성 우선순위 스펙

| 단계 | 기본 전략 | 비고 |
| --- | --- | --- |
| 유저/계정 생성 | 완전 합성 | 실사용자 복원 금지 |
| 이용 이력 생성 | 시나리오 기반 | 결제, 환불, 지급, 가챠 |
| 문의 생성 | 실데이터 우선 + 이용 이력 기반 합성 | 이용 이력으로 설명 가능해야 함 |
| 운영 메타값 부여 | AI 판정/규칙 부여 | `source_type`, `status`, `responder_type` 등 |

### 9.5 시나리오별 운영 데이터 생성 스펙

| 문의 유형 | 생성할 보조 테이블 | 필수 반영 사항 |
| --- | --- | --- |
| 결제 문의 | `payments` | 결제 상태, 상품, 결제수단, 결제시각 |
| 환불 문의 | `payments`, `refunds` | 원결제 존재, 환불 상태 및 요청 시각 |
| 아이템 미지급 문의 | `payments`, `item_delivery_logs` | 결제 여부, 지급 상태, 지급 지연 여부 |
| 이벤트/보상 문의 | `item_delivery_logs` | 지급 예정/실패/누락 표현 |
| 가챠 문의 | `gacha_logs` | 배너, 희귀도, 천장 카운트, 뽑기 시각 |

## 10. 권장 다음 단계

바로 필요한 작업은 아래 순서다.

1. 게임 유저 이용 시나리오와 상품/아이템 코드북을 확정한다.
2. 실제 문의 seed 정리 규칙과 개인정보 제거 규칙을 확정한다.
3. 이용 이력 기반 `qa_ticket` 생성 규칙을 확정한다.
4. 마지막에 AI 라벨 부여 기준을 정한다.

핵심은 `source_type`, `status`, `responder_type`, 길이, 재문의 여부를 먼저 분포 맞추는 것이 아니라, 게임 이용 데이터와 `qa_ticket` 본문을 먼저 만들고 그 후 AI가 판정하는 구조로 두는 것이다.
