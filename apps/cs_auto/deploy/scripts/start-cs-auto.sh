#!/bin/sh
set -eu

python -m uvicorn api.main:app \
  --host "${CS_AUTO_UVICORN_HOST}" \
  --port "${CS_AUTO_UVICORN_PORT}" &

exec nginx -g "daemon off;"
