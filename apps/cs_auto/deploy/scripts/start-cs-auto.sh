#!/bin/sh
set -eu

# The deployed backend currently imports `run_load_ticket`, but that symbol
# is not defined in `api.services.load_ticket`. Patch the copied source before
# boot so the API can start without requiring a backend tree edit here.
python - <<'PY'
from pathlib import Path

main_py = Path("/app/apps/cs_auto/backend/api/main.py")
text = main_py.read_text(encoding="utf-8")
patched = text.replace(
    "from api.services.load_ticket import get_review_tickets, get_ticket_detail, run_load_ticket",
    "from api.services.load_ticket import get_review_tickets, get_ticket_detail",
)
if patched != text:
    main_py.write_text(patched, encoding="utf-8")
PY

python -m uvicorn api.main:app \
  --host "${CS_AUTO_UVICORN_HOST}" \
  --port "${CS_AUTO_UVICORN_PORT}" &

exec nginx -g "daemon off;"
