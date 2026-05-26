from langchain.agents import create_agent
from config import settings


tools=[]
agent = create_agent(settings.openai_model, tools=tools)
