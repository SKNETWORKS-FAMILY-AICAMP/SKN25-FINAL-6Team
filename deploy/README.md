# Deploy Guide

This deploy layer runs the application containers and routes traffic through Nginx. PostgreSQL/pgvector is treated as an external database reachable through Tailscale.

For the MVP deployment, chatbot services are commented out until the real chatbot UI/API is implemented. Redis is also excluded because the current code does not use it. Only operation and dashboard are started by default.

## Runtime Services

```text
Docker Compose
|-- nginx
|-- operation-frontend
|-- operation-backend
|-- dashboard-frontend
`-- dashboard-backend

External network
`-- PostgreSQL / pgvector over Tailscale
```

The Compose file intentionally does not start PostgreSQL or Redis containers. The backend containers load `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` from `.env`.

## Required `.env`

Use a Tailscale IP or MagicDNS host for `DB_HOST`.

```env
DB_HOST=100.x.y.z
DB_PORT=5432
DB_USER=...
DB_PASSWORD=...
DB_NAME=...
DB_CONNECT_TIMEOUT=15
```

Do not set `DB_HOST=localhost` for Docker containers. Inside a container, `localhost` points to that container, not the Windows host or the Tailscale peer.

## Run

```bash
docker compose up -d --build
docker compose ps
```

## Check Database Reachability

Run this after the containers are up:

```bash
docker compose exec operation-backend python -c "import os, psycopg; psycopg.connect(host=os.environ['DB_HOST'], port=os.environ['DB_PORT'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], dbname=os.environ['DB_NAME'], connect_timeout=5).close(); print('db ok')"
```

If this fails, the container cannot reach the Tailscale database route. Fix the host networking/Tailscale route first, or run the app directly on Windows for local development.
