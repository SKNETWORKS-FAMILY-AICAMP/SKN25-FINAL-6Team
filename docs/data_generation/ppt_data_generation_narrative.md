# 데이터 생성 설계 설명

## 1. 한 줄 메시지

이번 데이터셋은 단순한 무작위 합성 데이터가 아니라, **실제 문의 분포를 기반으로 하고 논문에서 제안한 synthetic data generation 원칙을 게임 CS 도메인에 맞게 재설계한 결과물**이다.

발표에서는 아래 메시지가 핵심이다.

- 우리는 데이터가 없어서 아무 문장을 만든 것이 아니다.
- 실제 문의 구조와 운영 흐름을 먼저 분석한 뒤, 부족한 구간만 합성으로 보강했다.
- 합성 과정에서도 게임 도메인 맥락, 문의 발생 원인, 운영상 연결성, 개인정보 보호를 모두 고려했다.

## 2. 왜 이런 방식으로 만들었는가

게임 고객문의 데이터는 단순 텍스트 생성만으로는 품질이 확보되지 않는다.

- 결제, 환불, 아이템 미지급, 가챠, 제재 이의제기처럼 도메인별 맥락이 다르다.
- 같은 불만 문의라도 유저 상태, 계정 이력, 결제 이력에 따라 내용이 달라진다.
- 실제 운영 환경에서는 문의 본문만 중요한 것이 아니라, 그 문의가 어떤 게임 로그와 연결되는지가 중요하다.

따라서 이번 작업은 **문의 문장만 생성하는 접근이 아니라, 게임 이용 이력과 문의가 서로 설명되도록 만드는 데이터 설계**를 목표로 했다.

## 3. 논문 기반 설계 원칙

이번 설계는 세 가지 연구 흐름을 실무적으로 반영했다.

### 3.1 Self-Instruct 계열 아이디어 반영

핵심 반영 내용:

- 실제 데이터(seed)를 먼저 두고 확장한다.
- 부족한 케이스만 제한적으로 합성한다.
- 생성 후 필터링과 검증 단계를 반드시 둔다.

우리 프로젝트 적용:

- `qa_ticket` 실데이터 구조를 중심 seed로 사용했다.
- 전체를 새로 생성하지 않고, 실데이터 분포를 기준으로 축소·재구성했다.
- hard case, high-risk case는 별도 quota로 보강하는 방향을 택했다.

즉, **생성을 위한 생성이 아니라, 실제 분포 기반 보강**이라는 점이 중요하다.

### 3.2 Synthetic Persona / Human Simulation 계열 아이디어 반영

핵심 반영 내용:

- LLM은 평균적인 답변으로 쏠리기 쉽다.
- 따라서 극단 불만, 반복 민원, 긴급 문의 같은 케이스를 의도적으로 보강해야 한다.

우리 프로젝트 적용:

- 일반 문의만 복제하면 모델이 현실보다 너무 순한 문의에 익숙해질 수 있다고 판단했다.
- 그래서 환불 강경 요청, 보안 이슈, 계정 탈취 의심, 제재 이의제기, 결제 완료 후 미지급, 이벤트 보상 누락 같은 케이스를 별도 관리 대상으로 잡았다.
- 단순 비율 복제보다 **운영 리스크가 큰 문의를 놓치지 않는 데이터셋**을 만드는 쪽에 무게를 뒀다.

### 3.3 Synthetic UGC 평가 연구 반영

핵심 반영 내용:

- 합성 텍스트는 의미 보존, 스타일 보존, 다양성, 개인정보 보호를 함께 봐야 한다.
- 문장 수를 늘리는 것만으로는 좋은 데이터셋이 되지 않는다.

우리 프로젝트 적용:

- 의미 보존: 문의 원인과 요구사항이 실제 운영 로그로 설명되도록 구성했다.
- 스타일 보존: 커뮤니티/버그 문의 특유의 불만 표현, 반복 질문, 짧고 직설적인 문체를 유지하려고 했다.
- 다양성: 일반 문의 외에 반복 문의, 긴급 문의, 민감 문의를 포함했다.
- 개인정보 보호: 실제 식별정보는 복원하지 않고 가명/치환 방식으로 처리했다.

## 4. 게임 도메인을 어떻게 반영했는가

이번 데이터는 범용 CS 데이터가 아니라 **게임 서비스 운영 맥락을 가진 데이터**로 설계했다.

주요 반영 포인트:

- 계정 상태: 정상, 휴면, 제한 계정 여부가 문의 유형과 연결되도록 설계
- 결제 흐름: 결제 성공/실패/지연/중복 결제와 문의가 연결되도록 설계
- 아이템 지급: 구매 보상, 이벤트 보상, 지급 지연, 지급 실패를 분리
- 가챠 로그: 배너, 천장, 희귀도, 체감 불만이 문의로 이어질 수 있게 설계
- 제재/보안: 계정 탈취 의심, 이용 제한, 제재 이의 제기를 hard case로 반영

즉, **문의 텍스트만 게임처럼 보이게 만든 것이 아니라, 문의가 발생할 수밖에 없는 운영 배경까지 같이 구성**했다.

## 5. 실제 분포는 무엇을 기준으로 잡았는가

발표에서 강조할 포인트는 여기다.

이번 데이터셋의 문의 분포는 임의로 만든 것이 아니라, **네이버 카페의 실제 버그/문의 게시글 크롤링 데이터에서 확인한 패턴을 기준으로 설계**했다.

적용 방식:

- 문의 길이 분포
- 반복 문의 여부
- 불만 강도
- 커뮤니티 특유의 직설적 표현
- 계정 연결이 없는 문의 비율

이런 요소를 먼저 보고, 그 뒤에 필요한 범위만 synthetic generation으로 보강했다.

따라서 발표에서는 아래처럼 말하면 된다.

> “분포 자체를 임의로 상상해서 만든 것이 아니라, 네이버 카페 버그 문의 크롤링에서 관찰한 실제 문의 패턴을 기준으로 삼고, 부족한 케이스만 논문 기반 합성 전략으로 보강했습니다.”

## 6. 생성 대상과 생성 제외 대상을 분리한 이유

우리는 모든 테이블을 한 번에 생성하지 않았다. 실제 서비스 운영에 중요한 연결 구조만 우선 생성했다.

직접 생성한 핵심 테이블:

- `community_users`
- `game_accounts`
- `qa_ticket`
- `payments`
- `refunds`
- `item_delivery_logs`
- `gacha_logs`

이렇게 한 이유:

- 문의를 설명하는 최소 운영 근거를 확보하기 위해서
- 모델이 텍스트만이 아니라 운영 맥락까지 학습할 수 있게 하기 위해서
- 실무적으로 중요한 CS 시나리오를 우선 커버하기 위해서

즉, **범위를 의도적으로 통제해서 품질을 올리는 전략**을 택했다.

## 7. 품질 관리에서 무엇을 신경 썼는가

이번 작업에서 강조할 품질 관리 포인트는 다음과 같다.

### 7.1 데이터 정합성

- `qa_ticket.user_id`가 실제 유저와 연결되는지 확인
- `qa_ticket.account_id`가 nullable 특성을 유지하는지 확인
- 결제/환불/지급/가챠 로그가 실제 계정과 연결되는지 확인
- 시간 순서가 자연스러운지 확인
  - 유저 생성 < 계정 생성 < 운영 이벤트 < 문의 발생

### 7.2 운영 설명 가능성

- 결제 문의는 `payments`로 설명 가능해야 한다.
- 환불 문의는 `payments + refunds`로 설명 가능해야 한다.
- 아이템 미지급 문의는 `payments + item_delivery_logs`로 설명 가능해야 한다.
- 가챠 불만 문의는 `gacha_logs`와 연결 가능해야 한다.

즉, **문의 하나하나가 왜 발생했는지 운영 데이터로 역추적 가능한 구조**를 목표로 했다.

### 7.3 개인정보 보호

- 이메일, UID, 주문번호 등은 직접 복원하지 않았다.
- 실제 유저 식별이 가능한 정보는 제거 또는 치환했다.
- 실데이터 기반이라도 재식별 위험을 줄이는 방향으로 정리했다.

## 8. 우리가 강조할 차별점

발표에서는 아래 차별점을 명확히 말할 수 있다.

### 8.1 단순 LLM 문장 생성과 다르다

- 그냥 “게임 문의처럼 보이는 문장”을 많이 만든 것이 아니다.
- 실제 테이블 구조, FK 관계, 운영 이벤트를 같이 설계했다.

### 8.2 실제 분포를 무시하지 않았다

- 네이버 카페 버그 문의 크롤링 기반으로 실제 패턴을 먼저 봤다.
- 분포를 임의로 설정하지 않고, 관찰값을 기준으로 삼았다.

### 8.3 hard case를 의도적으로 챙겼다

- 평균적인 문의만 있으면 운영 리스크가 큰 케이스를 놓친다.
- 그래서 제재, 보안, 환불 분쟁, 지급 누락 같은 케이스를 별도 보강했다.

### 8.4 도메인 설명력이 있다

- 문의 텍스트와 게임 운영 로그가 서로 맞물린다.
- 이 구조 덕분에 분류, 라우팅, 응답 생성 실험에 더 적합하다.

## 9. PPT용 문장 예시

### 9.1 짧은 버전

“본 데이터셋은 단순 합성 텍스트가 아니라, 실제 문의 분포와 게임 운영 로그를 함께 고려해 설계한 게임 CS 특화 synthetic dataset입니다.”

### 9.2 분포 강조 버전

“문의 분포는 네이버 카페 버그 문의 크롤링에서 확인한 실제 패턴을 기준으로 설계했고, 부족한 hard case만 논문 기반 합성 전략으로 제한적으로 보강했습니다.”

### 9.3 품질 강조 버전

“문의 본문만 생성한 것이 아니라, 결제·환불·아이템 지급·가챠 로그까지 연결해 각 문의가 실제로 왜 발생했는지 설명 가능한 구조로 설계했습니다.”

### 9.4 프로페셔널 톤 버전

“우리는 synthetic data를 단순 증량 수단으로 사용하지 않았습니다. 실제 문의 분포, 게임 도메인 시나리오, 운영 로그 정합성, 개인정보 보호를 함께 고려해 실험 가능한 수준의 데이터셋으로 재구성했습니다.”

## 10. 발표 마무리 메시지

마지막 슬라이드나 구두 설명에서는 아래 메시지가 가장 안정적이다.

> “이번 데이터셋 구축의 핵심은 많이 만드는 것이 아니라, 실제 서비스처럼 동작하는 데이터를 만드는 것이었습니다. 그래서 실제 문의 패턴을 기준으로 분포를 잡고, 게임 도메인 운영 시나리오와 연결성을 설계한 뒤, 논문 기반 synthetic generation 원칙으로 부족한 구간만 보강했습니다.”

## 11. 논문 인용 위치 정리

아래는 `data/gen/docs/raw_pdf` 기준으로 실제 발표에서 인용 가능한 논문과 위치를 정리한 것이다.

### 11.1 `self-instruct.pdf`

논문:

- Wang et al., **SELF-INSTRUCT: Aligning Language Models with Self-Generated Instructions**, ACL 2023

발표에서 연결할 수 있는 주장과 위치:

- “실제 seed를 두고 데이터를 확장하는 synthetic generation 전략”
  - p.2, Figure 2
  - `175 seed tasks`로 시작하는 전체 파이프라인 도식이 제시됨
- “생성 후 filtering 단계가 반드시 들어간다”
  - p.3, Section 2
  - SELF-INSTRUCT를 `generating tasks`, `filtering the generated data`, `instruction tuning`의 파이프라인으로 설명
  - p.4, Section 2.3 직전
  - low-quality 또는 similar instruction을 제거하는 filtering 설명 포함
- “classification / non-classification을 나눠 생성한다”
  - p.2, Figure 2
  - `Classification Task Identification` 단계 명시
  - p.14, Supplemental A.1
  - seed task를 classification / non-classification으로 구분했다고 설명
- “소량 seed에서 대규모 synthetic instruction data를 만든다”
  - p.4, Table 1
  - `52,445 instructions`, `11,584 classification`, `40,861 non-classification`, `82,439 instances`
- “생성 데이터는 검증 없이 쓰는 것이 아니라 품질 점검이 필요하다”
  - p.5, Table 2
  - `All fields are valid 54%`, output validity `58%` 등 품질 검토 수치 제시
- “synthetic instruction 데이터가 실제 성능 개선에 기여한다”
  - p.6, Table 3
  - GPT-3 `ROUGE-L 6.8` 대비 `GPT3 SELF-INST 39.9`, `InstructGPT001 40.8`

우리 발표에서의 사용 방식:

- “우리는 무작정 문장을 만든 것이 아니라, seed 기반 확장과 filtering을 포함한 논문형 파이프라인을 게임 CS 데이터 설계에 맞게 적용했다.”

### 11.2 `Simulating Human Opinions with Large Language Model.pdf`

논문:

- Kaiser et al., **Simulating Human Opinions with Large Language Models: Opportunities and Challenges for Personalized Survey Data Modeling**, UMAP Adjunct 2025

발표에서 연결할 수 있는 주장과 위치:

- “synthetic persona 방식은 집단 경향은 어느 정도 재현하지만, 개별 응답과 분산은 한계가 있다”
  - p.2
  - synthetic sample이 `overall trends and individual-level variability`를 재현하는지 평가한다고 설명
  - p.3
  - binary agreement `78.64%`, rating agreement `78.65%`
- “LLM은 평균적이고 더 긍정적인 방향으로 쏠릴 수 있다”
  - p.3, Section 3
  - synthetic ratings가 실제보다 높게 나타났다는 결과
  - `well-known brands received more positive ratings`를 synthetic sample도 재현하지만, 전체적으로 synthetic rating이 더 높게 형성됨
- “전체 경향 재현만 보고 synthetic data를 신뢰하면 위험하다”
  - p.4, Discussion
  - aggregate pattern 재현 가능성과 함께 `considerable constraints`를 명시

우리 발표에서의 사용 방식:

- “그래서 우리는 평균적인 문의만 복제하지 않고, 반복 민원, 보안 이슈, 환불 분쟁 같은 hard case를 별도로 챙겼다.”
- “즉, LLM이 평탄하고 순한 데이터만 만들지 않도록 운영 리스크가 큰 케이스를 의도적으로 보강했다.”

### 11.3 `synthetic_data_generation.pdf`

논문:

- Chim, Ive, Liakata, **Evaluating Synthetic Data Generation from User Generated Text**, Computational Linguistics 2025

발표에서 연결할 수 있는 주장과 위치:

- “합성 UGC 평가는 의미 보존, 스타일 보존, 다양성/차이, 개인정보 보호를 함께 봐야 한다”
  - p.1, Abstract
  - `style preservation`, `meaning preservation`, `divergence`, `privacy` 축을 명시
- “synthetic text는 downstream task 성능까지 같이 평가해야 한다”
  - p.1-3
  - evaluation framework와 representative tasks를 함께 제시
  - p.20, Section 6.2
  - synthetic data로 학습한 downstream model 성능 비교
- “privacy를 강하게 주면 성능 저하 trade-off가 생긴다”
  - p.20
  - DP-BART가 author profiling risk를 크게 낮추지만 성능 trade-off가 있음을 설명
  - p.26, Section 7
  - strict privacy budget가 meaning/style preservation과 label validity를 해칠 수 있다고 정리
- “style preservation은 실제 task 성능과 연결된다”
  - p.21, Section 6.2.1
  - style preservation이 대부분의 task에서 성능에 도움이 된다고 설명
- “divergence는 privacy risk 완화와 연결된다”
  - p.22, Section 6.2.2
  - divergence가 높을수록 profiling / re-identification risk를 낮추는 방향이라고 설명

우리 발표에서의 사용 방식:

- “우리는 문장 개수만 늘리지 않고, 의미 보존, 실제 커뮤니티 문의 말투, 개인정보 보호, downstream 활용 가능성을 함께 고려했다.”

### 11.4 발표에서 바로 쓸 수 있는 인용 표기 예시

- “Self-Instruct는 소량 seed task에서 시작해 생성-필터링-튜닝 파이프라인으로 데이터를 확장하는 접근을 제안한다 (Wang et al., 2023, `self-instruct.pdf` p.2-4).”
- “LLM 기반 synthetic persona는 집단 평균 경향은 재현하지만, 실제보다 더 긍정적이고 평균적인 응답으로 쏠릴 수 있다 (Kaiser et al., 2025, `Simulating Human Opinions with Large Language Model.pdf` p.3-4).”
- “Synthetic UGC 평가는 의미 보존, 스타일 보존, divergence, privacy를 함께 봐야 하며, downstream task 성능까지 연결해서 판단해야 한다 (Chim et al., 2025, `synthetic_data_generation.pdf` p.1, p.20-22, p.26).”

### 11.5 발표 시 주의할 점

- “네이버 카페 버그 문의 크롤링 기반으로 분포를 잡았다”는 부분은 논문 인용이 아니라 **우리 프로젝트의 실데이터 기반 설계 근거**다.
- 논문은 이 설계가 왜 타당한지 설명하는 방법론 근거로 쓰고, 네이버 카페 크롤링은 실제 분포 근거로 분리해서 말하는 것이 가장 프로페셔널하다.
