# PPT 문장 + 인용 꼬리표

아래 문장들은 슬라이드 본문에 바로 붙일 수 있도록 짧게 정리한 버전이다.

## 1. 데이터 생성 방법 소개 슬라이드

- 본 데이터셋은 단순 문장 증량이 아니라, 실제 문의 구조를 seed로 삼아 생성-필터링-검증 단계를 거쳐 재구성한 게임 CS 특화 synthetic dataset이다. `(Wang et al., 2023, p.2-5)`
- Self-Instruct 계열 연구처럼 소량 seed에서 출발하되, 생성 결과를 그대로 쓰지 않고 filtering과 품질 검토를 포함하는 방식으로 설계했다. `(Wang et al., 2023, p.2-5)`
- 실제 서비스 데이터의 맥락을 반영하기 위해 문의 본문만이 아니라 유저, 계정, 결제, 환불, 아이템 지급, 가챠 로그까지 함께 설계했다. `(Project design based on game-domain schema)`

## 2. 왜 이런 방식이 필요한가 슬라이드

- 게임 고객문의는 텍스트만 맞으면 되는 문제가 아니라, 어떤 운영 이벤트 때문에 문의가 발생했는지까지 설명 가능해야 한다. `(Project design principle)`
- 따라서 우리는 문의 문장만 생성하지 않고, 문의가 운영 로그로 역추적 가능한 구조를 목표로 했다. `(Project design principle)`
- 이는 synthetic text를 평가할 때 의미 보존과 downstream 활용 가능성을 함께 봐야 한다는 연구 방향과도 맞닿아 있다. `(Chim et al., 2025, p.1, p.20-22)`

## 3. 논문 기반 설계 원칙 슬라이드

- Seed 기반 확장: 실제 문의 구조를 출발점으로 삼고 부족한 케이스만 제한적으로 보강했다. `(Wang et al., 2023, p.2-4)`
- Filtering 기반 품질 관리: 생성 데이터는 그대로 사용하지 않고 중복, 저품질, 비현실적 케이스를 걸러내는 접근을 따랐다. `(Wang et al., 2023, p.3-5)`
- Hard case 보강: 평균적인 사례만으로는 운영 리스크를 반영하기 어렵기 때문에 고위험 문의를 별도 관리 대상으로 두었다. `(Kaiser et al., 2025, p.3-4)`
- Meaning, style, privacy 동시 고려: 합성 데이터는 의미 보존, 말투 보존, 개인정보 보호, 실제 task 활용성을 함께 봐야 한다. `(Chim et al., 2025, p.1, p.20-22, p.26)`

## 4. 분포 설계 근거 슬라이드

- 문의 분포는 임의로 설정한 것이 아니라, 네이버 카페 버그 문의 크롤링에서 관찰한 실제 패턴을 기준으로 삼았다. `(Internal crawling-based distribution analysis)`
- 이후 논문 기반 synthetic generation 전략을 이용해 부족한 구간만 제한적으로 보강했다. `(Wang et al., 2023, p.2-5)`
- 즉, 분포는 실데이터 기반으로 잡고, 생성은 방법론적으로 통제하는 이중 구조를 택했다. `(Project methodology)`

## 5. 게임 도메인 반영 슬라이드

- 결제 성공 후 미지급, 환불 분쟁, 이벤트 보상 누락, 가챠 불만, 제재 이의제기처럼 게임 서비스에서 실제로 중요한 시나리오를 우선 반영했다. `(Project domain scenario design)`
- 계정 상태, 결제 흐름, 지급 로그, 가챠 기록이 문의 내용과 자연스럽게 연결되도록 설계해 도메인 설명력을 높였다. `(Project design based on game-domain schema)`
- 이를 통해 문의 텍스트만 게임처럼 보이게 만든 것이 아니라, 문의가 발생하는 운영 배경까지 함께 구성했다. `(Project design principle)`

## 6. Hard Case 필요성 슬라이드

- LLM 기반 synthetic persona는 집단 경향은 어느 정도 재현하지만, 실제보다 더 평균적이고 더 긍정적인 방향으로 수렴할 수 있다. `(Kaiser et al., 2025, p.3-4)`
- 따라서 일반 문의만 복제하면 환불 분쟁, 보안 이슈, 반복 민원 같은 고위험 케이스를 놓칠 수 있다. `(Kaiser et al., 2025, p.4)`
- 우리는 이런 한계를 보완하기 위해 hard case를 별도 quota로 관리했다. `(Project data curation policy)`

## 7. 품질 관리 슬라이드

- 각 문의는 가능한 한 실제 운영 데이터로 설명 가능하도록 설계했다. 예를 들어 결제 문의는 payments, 환불 문의는 refunds, 미지급 문의는 item delivery logs와 연결된다. `(Project integrity validation)`
- 또한 synthetic UGC 연구에서 제안하듯 의미 보존, 스타일 보존, 개인정보 보호, downstream 활용 가능성을 함께 고려했다. `(Chim et al., 2025, p.1, p.20-22, p.26)`
- 즉, 문장을 많이 만드는 것보다 실험 가능한 품질의 데이터를 만드는 데 초점을 맞췄다. `(Project methodology)`

## 8. 개인정보 보호 슬라이드

- 실제 문의 구조를 참고했더라도 이메일, UID, 주문번호 등 직접 식별 가능한 정보는 복원하지 않고 제거 또는 치환했다. `(Project privacy policy)`
- 이는 synthetic UGC 평가에서 privacy risk를 별도 축으로 봐야 한다는 연구 흐름과 일치한다. `(Chim et al., 2025, p.1, p.22, p.26-27)`

## 9. 차별점 슬라이드

- 우리는 단순히 게임 문의처럼 보이는 문장을 생성한 것이 아니라, 실제 분포와 운영 로그 정합성을 함께 반영한 데이터셋을 구축했다. `(Project contribution)`
- 실데이터 기반 분포, 논문 기반 생성 전략, 게임 도메인 시나리오, hard case 보강을 함께 적용했다는 점이 핵심 차별점이다. `(Wang et al., 2023, p.2-5; Kaiser et al., 2025, p.3-4; Chim et al., 2025, p.1, p.20-22)`

## 10. 마무리 슬라이드

- 이번 데이터셋 구축의 목표는 데이터를 많이 만드는 것이 아니라, 실제 서비스처럼 동작하는 데이터를 만드는 것이었다. `(Project objective)`
- 그래서 실제 문의 패턴을 기준으로 분포를 잡고, 게임 도메인 운영 시나리오를 연결한 뒤, 논문 기반 synthetic generation 원칙으로 부족한 구간만 보강했다. `(Wang et al., 2023, p.2-5; Project methodology)`

## 11. 발표 시 표기 규칙

- 논문 기반 문장: `(Wang et al., 2023, p.4)`처럼 표기
- 복수 페이지: `(Chim et al., 2025, p.20-22)`
- 프로젝트 자체 근거: `(Internal crawling-based distribution analysis)` 또는 `(Project design principle)`처럼 표기

## 12. 바로 쓰기 좋은 짧은 문장

- 실데이터 기반 분포, 논문 기반 보강 전략으로 설계한 게임 CS synthetic dataset `(Wang et al., 2023, p.2-5)`
- 네이버 카페 버그 문의 패턴을 기준으로 분포를 설계 `(Internal crawling-based distribution analysis)`
- hard case를 별도 quota로 관리해 운영 리스크를 반영 `(Kaiser et al., 2025, p.3-4)`
- 의미, 스타일, 프라이버시, downstream 성능을 함께 고려 `(Chim et al., 2025, p.1, p.20-22, p.26)`
