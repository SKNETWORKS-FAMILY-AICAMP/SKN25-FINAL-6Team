#!/bin/sh
set -eu

python -m uvicorn api.main:app \
  --host "${CHATBOT_UVICORN_HOST}" \
  --port "${CHATBOT_UVICORN_PORT}" &

exec nginx -g "daemon off;"
