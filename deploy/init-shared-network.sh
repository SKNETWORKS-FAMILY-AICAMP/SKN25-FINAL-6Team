#!/bin/sh
set -eu

NETWORK_NAME="${DEPLOY_SHARED_NETWORK:-skn25-shared}"

if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  echo "Docker network already exists: $NETWORK_NAME"
else
  docker network create "$NETWORK_NAME"
  echo "Created Docker network: $NETWORK_NAME"
fi
