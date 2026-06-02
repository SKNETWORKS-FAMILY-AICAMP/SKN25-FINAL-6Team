# cs_auto Split Docker Setup

## Overview

`cs_auto` is split into two independent Docker Compose stacks:

1. `cs_auto` web stack
2. `Airflow` batch stack

They are intentionally separated so the operator UI and batch scheduler do not share the same web entrypoint.

## Files

- `apps/cs_auto/deploy/docker-compose.cs-auto.yml`
- `apps/cs_auto/deploy/docker-compose.airflow.yml`

## 1. cs_auto Web Stack

Services:

- `cs-auto-backend`
- `cs-auto-nginx`

Runtime URLs:

- UI: `http://localhost:8088/cs-auto/`
- API health: `http://localhost:8088/cs-auto/api/health`
- Backend direct: `http://localhost:8000/health`

Run:

```powershell
docker compose -f apps/cs_auto/deploy/docker-compose.cs-auto.yml up --build -d
```

Stop:

```powershell
docker compose -f apps/cs_auto/deploy/docker-compose.cs-auto.yml down
```

## 2. Airflow Stack

Services:

- `airflow-postgres`
- `airflow-init`
- `airflow-webserver`
- `airflow-scheduler`

Runtime URL:

- Airflow UI: `http://localhost:8080`

Default Airflow admin account:

- username: `admin`
- password: `admin`

Run:

```powershell
docker compose -f apps/cs_auto/deploy/docker-compose.airflow.yml up --build -d
```

Stop:

```powershell
docker compose -f apps/cs_auto/deploy/docker-compose.airflow.yml down
```

## Environment

Both stacks read the repository root `.env`:

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

These values are for the `cs_auto` application database.

The Airflow metadata database is separate and is created by the `airflow-postgres` service inside the Airflow stack.

## Notes

- The `cs_auto` frontend remains static and is served by nginx.
- The frontend already calls `/cs-auto/api/...`, so the nginx stack preserves that route.
- The Airflow stack does not expose the `cs_auto` frontend.
- The two stacks can be started independently.
