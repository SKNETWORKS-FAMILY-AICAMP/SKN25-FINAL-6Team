from __future__ import annotations

from rootsetting import ensure_project_root_on_path


ensure_project_root_on_path()

from dashboard.agent import agent as dashboard_agent
from operation.agent import agent as operation_agent


def last_message_text(result: dict) -> str:
    messages = result.get("messages", [])
    last_message = messages[-1]
    content = last_message.get("content", "") if isinstance(last_message, dict) else getattr(last_message, "content", "")
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def resolve_operation_output() -> str:
    result = operation_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Run STEP1 and STEP2 with the seed payload. "
                        "Return ticket_analysis, answer_draft, evidence_docs, "
                        "safety_results, approval_result, and final_outcome."
                    ),
                }
            ]
        }
    )
    return last_message_text(result)


def main() -> None:
    operation_output = resolve_operation_output()
    result = dashboard_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Run STEP3 and observability with the seed payload. "
                        "Use this operation output as the upstream result:\n\n"
                        f"{operation_output}\n\n"
                        "Return the final dashboard output."
                    ),
                }
            ]
        }
    )
    print(last_message_text(result))


if __name__ == "__main__":
    main()
