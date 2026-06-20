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

All compose files assume the build context is the repository root (`..` from this directory).
They copy shared code from `common/`, so run compose commands from `deploy/` or keep the same `--project-directory`/file layout.

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

The Airflow container uses a custom entrypoint script that applies
`AIRFLOW_ADMIN_*` values before starting the webserver/scheduler.

Airflow admin login is now applied from `.env` on every container start. Set:

```sh
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=change-me
AIRFLOW_ADMIN_FIRSTNAME=Admin
AIRFLOW_ADMIN_LASTNAME=User
AIRFLOW_ADMIN_EMAIL=admin@example.com
```

If you want the weekly report DAG to send Slack messages, also set:

```sh
DASHBOARD_WEEKLY_REPORT_CHANNEL=<channel id or name>
DASHBOARD_SLACK_BOT_TOKEN=<bot token>
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
