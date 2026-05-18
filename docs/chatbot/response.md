# Chatbot Final Response

이 폴더는 LangGraph workflow의 마지막 사용자-facing 답변 정리 node를 담습니다.

Safety Layer는 답변을 승인/차단/검토 등의 decision으로 분류하고, Final Response Layer는 그 decision을 실제 사용자에게 보낼 최종 답변으로 변환합니다.

## 현재 파일

| 파일 | 노드 함수 | 역할 |
|------|-----------|------|
| `final_response.py` | `final_response_node` | `safety_action`에 따라 `final_answer` 생성 |
| `__init__.py` | - | response package marker |

## 입력

```text
answer_draft
safety_action
ticket_id
raw_content
```

## 출력

```python
{
    "final_answer": str,
}
```

## Decision 처리

```text
AUTO_RESPONSE
  -> answer_draft를 최종 답변으로 사용

BLOCK_RESPONSE
  -> 안전 상담을 위한 차단 안내 고정 답변 반환

SAFE_FALLBACK
  -> 일반 안내 및 담당자 확인 안내 고정 답변 반환

MASKING
  -> 현재 baseline에서는 fallback 답변 반환
  -> 향후 마스킹된 답변을 다시 safety 검사한 뒤 최종 답변으로 사용

REVIEW_QUEUE
  -> 담당자 검토 접수 안내 고정 답변 반환
```

## 저장 정책

현재 baseline은 `final_answer`를 state에 남기는 단계까지만 구현합니다.

향후 실제 DB 연동 시에는 아래 형태로 `QA_ticket.raw_content`에 append합니다.

```text
Q: {raw_content}
A: {final_answer}
```

Safety Layer의 `decision_type`은 `safety_results`에 저장하고, 사용자에게 실제로 나간 답변 본문은 Final Response 단계에서 `QA_ticket.raw_content`에 누적하는 방향입니다.
