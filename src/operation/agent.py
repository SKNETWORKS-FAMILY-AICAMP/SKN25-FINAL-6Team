# runners/run_operation.py 11번째 줄이 아래 경로로 이 파일을 참조한다.
# from operation.agent import agent as operation_agent
# 실제 구현은 step12agent/agent.py에 있으며, 여기서는 그대로 노출만 한다.
from operation.step12agent.agent import agent

__all__ = ["agent"]
