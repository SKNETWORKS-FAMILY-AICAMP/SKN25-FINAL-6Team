from __future__ import annotations

from rootsetting import ensure_project_root_on_path


ensure_project_root_on_path()

import json

from data.seed_payload import FIRST_INPUT_PAYLOAD
from operation.agent import agent as operation_agent


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
                        "Run STEP1 and STEP2 from the first input payload only. "
                        "Do not use any database. Perform routing and RAG with the model, "
                        "using payload data and retrieved payload documents.\n\n"
                        "First input payload:\n"
                        f"{json.dumps(FIRST_INPUT_PAYLOAD, ensure_ascii=True, indent=2)}"
                    ),
                }
            ]
        }
    )
    print(last_message_text(result))


if __name__ == "__main__":
    main()
