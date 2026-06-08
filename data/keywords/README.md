# CS Auto Analysis Keywords

`apps/cs_auto/backend/agents/analysis_agent.py`가 사용하는 규칙 기반 분석 키워드 사전이다.

## 파일 구조

- `category/*.yaml`: 문의 카테고리 분류 키워드
- `sentiment/*.yaml`: 감성 판단 키워드
- `risk/*.yaml`: 위험도 판단 키워드

## 구조

```yaml
keywords:
  - 결제
  - 결제 오류
```

각 파일은 `keywords` mapping 아래에 sequence를 두는 구조다. 게임 CS 문의에서 자주 나오는 결제, 환불, 계정, 버그, 가챠, 정책 표현을 기준으로 관리한다.
