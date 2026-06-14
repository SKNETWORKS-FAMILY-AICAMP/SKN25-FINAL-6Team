#!/bin/sh
set -eu

# Run this script from the deploy directory on AWS:
#   cd deploy
#   sh ./deploy-down.sh
#
# This stops the deployment stacks created by deploy-all.sh.

# Move to the directory where this script lives so relative paths stay stable.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "Error: neither 'docker compose' nor 'docker-compose' is available."
  exit 1
fi

echo "[1/5] Stop shared nginx"
# Stop the public entrypoint first so no new requests arrive during shutdown.
$COMPOSE_CMD --env-file .env -f docker-compose.nginx.yml down

echo "[2/5] Stop airflow"
$COMPOSE_CMD --env-file .env -f docker-compose.airflow.yml down

echo "[3/5] Stop cs_auto backend"
$COMPOSE_CMD --env-file .env -f docker-compose.cs-auto.yml down

echo "[4/5] Stop chatbot backend"
$COMPOSE_CMD --env-file .env -f docker-compose.chatbot.yml down

echo "[5/5] Remove shared Docker network if unused"
# This may fail if something is still attached to the network, so keep shutdown
# successful and print a clear message instead of aborting.
NETWORK_NAME="${DEPLOY_SHARED_NETWORK:-skn25-shared}"
if docker network rm "$NETWORK_NAME" >/dev/null 2>&1; then
  echo "Removed Docker network: $NETWORK_NAME"
else
  echo "Skipped removing Docker network: $NETWORK_NAME"
fi

echo "Done. Current container status:"
docker ps
