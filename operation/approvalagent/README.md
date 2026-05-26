# Approval Agent

`approvalagent/`는 STEP2에서 생성된 답변 초안을 검토하고, 자동 승인 여부 또는 운영자 검토 필요 여부를 판단하는 Approval Gate 전용 디렉터리다.

## 담당 범위

`docs/operation_dashboard.md` 기준으로 다음 단계를 맡는다.

- 답변 초안 검토
- 근거 문서 일치 여부 확인
- hallucination, toxicity, policy violation 같은 안전성 판단
- `approved`, `human_review`, `urgent_alert` 중 어느 경로로 보낼지 결정

## 기대 입력

이 에이전트는 아래와 같은 STEP1/STEP2 산출물을 입력으로 받는 구조가 적절하다.

- `ticket_analysis`
- `answer_draft`
- `evidence_docs`

문서 설계상 필요하면 원문 문의와 계정/결제 로그도 함께 참조할 수 있다.

## 기대 출력

Approval Gate 이후에는 최소한 아래 결과가 만들어져야 한다.

- `safety_results`
- `approval_result`
- `final_outcome` 또는 human review 요청 정보

이 출력은 이후 `dashboard/`의 STEP3 집계와 인사이트 생성에 사용된다.

## 판단 기준

문서 기준으로 이 디렉터리는 아래 항목을 확인해야 한다.

- 초안이 근거 문서와 일치하는가
- 허위 사실 가능성이 높은가
- 정책 위반 표현이 포함되는가
- 즉시 운영자 개입이 필요한 고위험 문의인가

예를 들어 결제는 성공했지만 유료 아이템 미지급이 반복되는 경우는 `urgent_alert` 또는 최소 `human_review`로 보내는 구조가 자연스럽다.

## 파일 설명

- `agent.py`: 승인 전용 agent 구성 진입점
- `tools.py`: safety check, 승인 판단, 결과 포맷팅 도구 위치
- `prompts.py`: 승인 기준과 human-in-the-loop 지시문 위치

## 현재 상태

현재 이 디렉터리의 구현 파일은 모두 비어 있다.

- `agent.py`: 0 bytes
- `tools.py`: 0 bytes
- `prompts.py`: 0 bytes

즉, README는 설계 의도와 필요한 책임을 정리하는 역할을 하며, 실제 승인 로직은 아직 작성되지 않았다.

## 구현 방향

추후 구현 시 아래 순서로 채우는 것이 적절하다.

1. STEP2 출력 스키마 입력 받기
2. 근거-초안 일치성 검사
3. safety score 계산 또는 룰 기반 판정
4. `approval_result` 결정
5. `safety_results`와 최종 운영 액션 포맷 반환

## 관련 문서

- 상위 모듈 개요: `operation/README.md`
- 전체 플로우: `docs/operation_dashboard.md`
- 데이터 모델: `docs/ddl.md`
