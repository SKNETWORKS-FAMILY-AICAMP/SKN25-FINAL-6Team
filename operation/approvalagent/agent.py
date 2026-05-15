from langchain.agents import create_agent

from config import settings
from operation.approvalagent.prompts import APPROVAL_SYSTEM_PROMPT
from operation.approvalagent.tools import tools


agent = create_agent(
    settings.openai_model,
    tools=tools,
    system_prompt=APPROVAL_SYSTEM_PROMPT,
)
