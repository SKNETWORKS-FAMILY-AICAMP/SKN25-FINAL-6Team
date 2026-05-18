from __future__ import annotations

import json

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from config import PAYLOAD_MARKER
from data.seed_payload import FIRST_INPUT_PAYLOAD
from operation.agent import agent as operation_agent
from operation.step12agent.prompts import RUN_INSTRUCTION



def main() -> None:
    """seed_payload 고정 데이터를 입력으로 step12agent를 1회 실행하고 결과를 출력한다.

    실 DB 연동 전 임시 방식; 연동 완료 후 DB에서 QA_ticket을 읽는 방식으로 교체 예정.
    """
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
    print(result.get("answer_draft", ""))


if __name__ == "__main__":
    main()
