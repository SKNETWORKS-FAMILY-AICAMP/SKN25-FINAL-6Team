# Deploy Guide

현재 배포 기준점은 루트 [docker-compose.yml](/abs/path/C:/SKN25-FINAL-6Team/docker-compose.yml) 입니다.

이 앱은 다음 구성으로 올라갑니다.

- `chatbot-backend`: FastAPI / Uvicorn
- `chatbot-frontend`: React / Vite dev server
- `nginx`: `/chatbot` 및 `/chatbot/api` 프록시

## Runtime Paths

- UI: `http://localhost/chatbot/`
- API health: `http://localhost/chatbot/api/health`

## Compose Notes

- compose는 각 앱 디렉터리를 그대로 마운트하는 개발형 구성입니다.
- 백엔드는 `/app/apps/chatbot/backend`를 working directory로 사용합니다.
- Python import를 위해 `PYTHONPATH=/app/packages/common-python/src:/app/apps/chatbot/backend`를 사용합니다.
- 프런트는 `VITE_CHATBOT_API_BASE_URL=http://chatbot-backend:8000`로 API를 바라봅니다.

## Required `.env`

루트 `.env`에 최소한 아래 값이 필요합니다.

```env
DB_HOST=
DB_PORT=5432
DB_USER=
DB_PASSWORD=
DB_NAME=
LLM_API_KEY=
LLM_MODEL=
```

## Run

```bash
docker compose up -d
docker compose ps
```

## Important

- Docker Desktop daemon이 실행 중이어야 합니다.
- 컨테이너 내부에서 `pip install -r requirements.txt`와 `npm ci`가 실행됩니다.
- `DB_HOST=localhost`는 컨테이너 환경에서 사용하면 안 됩니다.
- 현재 공용 nginx 설정은 `apps/chatbot/deploy/nginx/default.conf`를 사용합니다.
