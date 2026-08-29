#!/usr/bin/env bash
# Runs backend (:1001) and the Vite dev server (:5173) together.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKEND_PY="backend/.venv/bin/python"
[ -x "$BACKEND_PY" ] || { echo "Create the venv first (see README)"; exit 1; }

# ARP + binding :1001 need privileges. Prefer file capabilities on the venv python.
REALPY=$(readlink -f "$BACKEND_PY")
if ! getcap "$REALPY" | grep -q cap_net_raw; then
  echo ">> Granting raw-socket + privileged-port capability to $REALPY"
  sudo setcap 'cap_net_raw,cap_net_admin,cap_net_bind_service+eip' "$REALPY"
fi

( cd backend && exec "$REALPY" run.py --reload ) &
BACK=$!
( cd frontend && exec npm run dev ) &
FRONT=$!

trap 'kill $BACK $FRONT 2>/dev/null || true' EXIT INT TERM
wait
