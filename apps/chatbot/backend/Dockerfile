FROM python:3.12-slim

WORKDIR /app

COPY packages/common-python /app/packages/common-python
COPY apps/chatbot/backend /app/apps/chatbot/backend

WORKDIR /app/apps/chatbot/backend

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

ENV PYTHONPATH=/app/packages/common-python/src:/app/apps/chatbot/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
