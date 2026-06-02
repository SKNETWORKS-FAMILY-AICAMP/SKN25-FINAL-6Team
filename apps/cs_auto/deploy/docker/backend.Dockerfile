FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages/common-python/src:/app/apps/cs_auto/backend

WORKDIR /app/apps/cs_auto/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY packages/common-python /app/packages/common-python
COPY apps/cs_auto/backend /app/apps/cs_auto/backend

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
