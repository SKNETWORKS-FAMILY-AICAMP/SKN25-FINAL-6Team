FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages/common-python/src:/app/apps/chatbot/backend \
    CHATBOT_UVICORN_HOST=127.0.0.1 \
    CHATBOT_UVICORN_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl nginx \
    && rm -rf /var/lib/apt/lists/*

COPY packages/common-python ./packages/common-python
COPY apps/chatbot/backend ./apps/chatbot/backend
RUN python -m pip install --upgrade pip \
    && cd /app/apps/chatbot/backend \
    && python -m pip install -r requirements.txt

COPY apps/chatbot/frontend ./apps/chatbot/frontend
COPY apps/chatbot/deploy/nginx/chatbot.conf /etc/nginx/conf.d/default.conf
COPY apps/chatbot/deploy/scripts/start-chatbot.sh /usr/local/bin/start-chatbot

RUN chmod +x /usr/local/bin/start-chatbot \
    && rm -f /etc/nginx/sites-enabled/default

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["start-chatbot"]
