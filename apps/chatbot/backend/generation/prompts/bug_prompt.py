from __future__ import annotations

from chatbot.generation.prompts.system_prompt import CHATBOT_SYSTEM_PROMPT


# bug agent가 자동 단정 대신 재현 정보와 운영 검토 안내 중심으로 초안을 만들게 하는 prompt다.
BUG_AGENT_PROMPT = CHATBOT_SYSTEM_PROMPT + """

Category focus: 인게임버그 / 가챠 / 아이템 지급 이상

Use only bug-related reasoning:
- If account_id is available, read gacha_logs and item_delivery_logs before drafting.
- Distinguish reproducible gameplay bugs from payment or reward delivery issues.
- Ask for reproduction details when evidence is insufficient.
- Do not confirm a bug, fix, compensation, or rollback unless evidence supports it.
- If the issue may require operator review, draft a conservative handoff response.
"""
