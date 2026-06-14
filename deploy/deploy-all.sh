#!/bin/sh
set -eu

# Run this script from the deploy directory on AWS:
#   cd deploy
#   sh ./deploy-all.sh
#
# Prerequisites:
# - .env must already exist in this directory.
# - WEB_HTTP_PORT should usually be 80 on AWS.
# - DB/LLM related environment variables must be filled in .env.

# Move to the directory where this script lives so relative paths stay stable.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/5] Ensure shared Docker network exists"
# The nginx/chatbot/cs_auto/airflow stacks are started as separate compose
# projects, so they need one shared external network to talk to each other.
sh ./init-shared-network.sh

echo "[2/5] Start chatbot backend"
# Starts the chatbot backend container only.
docker-compose --env-file .env -f docker-compose.chatbot.yml up -d --build

echo "[3/5] Start cs_auto backend"
# Starts the cs_auto backend container only.
docker-compose --env-file .env -f docker-compose.cs-auto.yml up -d --build

echo "[4/5] Start airflow"
# Starts the cs_auto Airflow container only.
docker-compose --env-file .env -f docker-compose.airflow.yml up -d --build

echo "[5/5] Start shared nginx"
# Starts the shared nginx that serves frontend files and proxies API requests
# to chatbot-backend and cs-auto-backend over the shared Docker network.
docker-compose --env-file .env -f docker-compose.nginx.yml up -d --build

echo "Done. Current container status:"
docker ps
