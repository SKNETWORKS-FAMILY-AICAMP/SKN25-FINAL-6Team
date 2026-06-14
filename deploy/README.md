# Deploy

AWS deployment is split by service. Each machine runs its own stack:

- `chatbot`: `chatbot-nginx` + `chatbot-backend`
- `cs_auto`: `cs-auto-nginx` + `cs-auto-backend`
- `airflow`: `cs-auto-airflow`

There is no shared external Docker network and no shared `web-nginx`.

## Files

- `docker-compose.chatbot.yml`: chatbot stack with dedicated nginx
- `docker-compose.cs-auto.yml`: cs_auto stack with dedicated nginx
- `docker-compose.airflow.yml`: cs_auto Airflow
- `.env.example`: shared environment example
- `.env.chatbot.example`: chatbot server example
- `.env.cs-auto.example`: cs_auto server example
- `.env.airflow.example`: airflow server example
- `deploy-all.sh`: starts all stacks on one host
- `deploy-down.sh`: stops all stacks on one host

## First Run

```sh
cd deploy
cp .env.example .env
```

Minimum required values in `.env`:

- `DB_HOST`
- `DB_PASSWORD`
- `LLM_API_KEY`
- `CS_AUTO_API_CORS_ORIGINS`

When running multiple stacks on one host, do not reuse port `80`:

```sh
CHATBOT_HTTP_PORT=8080
CS_AUTO_HTTP_PORT=8081
CS_AUTO_AIRFLOW_PORT=18080
```

When running each stack on its own EC2 instance, keeping `80` is fine.

## Start

Chatbot machine:

```sh
docker compose --env-file .env -f docker-compose.chatbot.yml up -d --build
```

CS Auto machine:

```sh
docker compose --env-file .env -f docker-compose.cs-auto.yml up -d --build
```

Airflow machine:

```sh
docker compose --env-file .env -f docker-compose.airflow.yml up -d --build
```

If you want the weekly report DAG to send Slack messages, also set:

```sh
DASHBOARD_WEEKLY_REPORT_CHANNEL=<channel id or name>
DASHBOARD_SLACK_BOT_TOKEN=<bot token>
```

Single-host convenience:

```sh
sh ./deploy-all.sh
```

## Status

```sh
docker compose --env-file .env -f docker-compose.chatbot.yml ps
docker compose --env-file .env -f docker-compose.cs-auto.yml ps
docker compose --env-file .env -f docker-compose.airflow.yml ps
```

## Stop

```sh
docker compose --env-file .env -f docker-compose.chatbot.yml down
docker compose --env-file .env -f docker-compose.cs-auto.yml down
docker compose --env-file .env -f docker-compose.airflow.yml down
```

## Runtime Paths

Chatbot machine:

- `http://<HOST>:<CHATBOT_HTTP_PORT>/chatbot/`
- `http://<HOST>:<CHATBOT_HTTP_PORT>/chatbot/api/health`

CS Auto machine:

- `http://<HOST>:<CS_AUTO_HTTP_PORT>/cs-auto/`
- `http://<HOST>:<CS_AUTO_HTTP_PORT>/cs-auto/api/health`

Airflow machine:

- `http://<HOST>:<CS_AUTO_AIRFLOW_PORT>/`

## Notes

- `chatbot` and `cs_auto` now build separate nginx images, so each machine only carries the frontend assets it serves.
- `chatbot` and `cs_auto` no longer depend on cross-compose networking.
- Do not set `DB_HOST=localhost` unless the DB is inside the same container.
