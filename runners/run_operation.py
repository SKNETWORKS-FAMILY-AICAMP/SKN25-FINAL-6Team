from __future__ import annotations

import json

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from config import PAYLOAD_MARKER
from data.seed_payload import FIRST_INPUT_PAYLOAD
from operation.agent import agent as operation_agent
from operation.step12agent.prompts import RUN_INSTRUCTION


def last_message_text(result: dict) -> str:
    messages = result.get("messages", [])
    last_message = messages[-1]
    content = last_message.get("content", "") if isinstance(last_message, dict) else getattr(last_message, "content", "")
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def main() -> None:
    result = operation_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{RUN_INSTRUCTION}"
                        f"{PAYLOAD_MARKER}{json.dumps(FIRST_INPUT_PAYLOAD, ensure_ascii=True, indent=2)}"
                    ),
                }
            ]
        }
    )
    print(last_message_text(result))


if __name__ == "__main__":
    main()
