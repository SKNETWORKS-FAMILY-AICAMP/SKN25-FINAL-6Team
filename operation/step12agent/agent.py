from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from config import settings

model = ChatOpenAI(model=settings.openai_model)


tools=[]
agent = create_agent(model, tools=tools)
