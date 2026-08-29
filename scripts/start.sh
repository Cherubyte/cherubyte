#!/usr/bin/env bash
# Production-style start: builds the frontend, serves everything from :1001.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKEND_PY="backend/.venv/bin/python"
REALPY=$(readlink -f "$BACKEND_PY")

if ! getcap "$REALPY" 2>/dev/null | grep -q cap_net_raw; then
  echo ">> Granting raw-socket + privileged-port capability to $REALPY"
  sudo setcap 'cap_net_raw,cap_net_admin,cap_net_bind_service+eip' "$REALPY"
fi

( cd frontend && npm install --omit=dev --no-audit --no-fund && npm run build )
cd backend && exec "$REALPY" run.py
