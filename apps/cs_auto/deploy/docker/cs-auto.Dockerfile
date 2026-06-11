FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages/common-python/src:/app/apps/cs_auto/backend \
    CS_AUTO_UVICORN_HOST=127.0.0.1 \
    CS_AUTO_UVICORN_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl nginx \
    && rm -rf /var/lib/apt/lists/*

COPY apps/cs_auto/backend/requirements.txt /tmp/cs-auto-requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/cs-auto-requirements.txt

COPY packages/common-python/src ./packages/common-python/src
COPY apps/cs_auto/backend ./apps/cs_auto/backend
COPY apps/cs_auto/frontend ./apps/cs_auto/frontend
COPY data/sql ./data/sql
COPY data/keywords ./data/keywords
COPY apps/cs_auto/deploy/nginx/cs_auto.conf /etc/nginx/conf.d/default.conf
COPY apps/cs_auto/deploy/scripts/start-cs-auto.sh /usr/local/bin/start-cs-auto

RUN chmod +x /usr/local/bin/start-cs-auto \
    && rm -f /etc/nginx/sites-enabled/default

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/cs-auto/health || exit 1

CMD ["start-cs-auto"]
