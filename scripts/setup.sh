#!/usr/bin/env bash
# NetScan — one-shot setup after cloning.
#
# Builds the panel (backend venv + compiled frontend), creates the database and
# the first admin account. Optionally builds the bundled agent and installs the
# systemd unit so it runs at boot.
#
#   ./scripts/setup.sh                       # interactive
#   ./scripts/setup.sh --service             # + install & start at boot
#   ./scripts/setup.sh --service --agent     # + a local scanner on this box
#
#   NETSCAN_ADMIN_USERNAME=me NETSCAN_ADMIN_PASSWORD=secret123 \
#     ./scripts/setup.sh --service           # unattended
#
# Flags:
#   --service    install + start the systemd unit at the end
#   --agent      also build the bundled agent venv (a scanner on this machine)
#   --no-admin   skip creating the admin account
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

WANT_SERVICE=0 WANT_AGENT=0 WANT_ADMIN=1
for a in "$@"; do
  case "$a" in
    --service)  WANT_SERVICE=1 ;;
    --agent)    WANT_AGENT=1 ;;
    --no-admin) WANT_ADMIN=0 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a  (try --help)"; exit 2 ;;
  esac
done

# --- prerequisites ------------------------------------------------------------
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
python3 - <<'PY' || { echo "Python 3.11+ required"; exit 1; }
import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
command -v node >/dev/null || { echo "Node.js 20+ not found"; exit 1; }
command -v npm  >/dev/null || { echo "npm not found"; exit 1; }

# --- panel -------------------------------------------------------------------
echo ">> Backend venv + dependencies"
python3 -m venv backend/.venv
backend/.venv/bin/pip -q install --upgrade pip
backend/.venv/bin/pip -q install -r backend/requirements.txt
backend/.venv/bin/pip -q install ./protocol

echo ">> Frontend build"
( cd frontend && npm install --no-audit --no-fund && npm run build )

echo ">> Database schema"
( cd backend && .venv/bin/python manage.py init-db )

if [ "$WANT_ADMIN" = 1 ]; then
  echo ">> Initial admin account"
  ADMIN_USER=${NETSCAN_ADMIN_USERNAME:-}
  if [ -z "$ADMIN_USER" ] && [ -t 0 ]; then
    read -rp "   Admin username [admin]: " ADMIN_USER
  fi
  ( cd backend && .venv/bin/python manage.py create-admin "${ADMIN_USER:-admin}" )
fi

# --- optional bundled agent ------------------------------------------------
if [ "$WANT_AGENT" = 1 ]; then
  echo ">> Agent venv + dependencies"
  python3 -m venv agent/.venv
  agent/.venv/bin/pip -q install --upgrade pip
  agent/.venv/bin/pip -q install -r agent/requirements.txt
  agent/.venv/bin/pip -q install ./protocol
fi

# --- optional systemd unit ------------------------------------------------
if [ "$WANT_SERVICE" = 1 ]; then
  echo ">> Installing /etc/systemd/system/netscan.service"
  sed -e "s#__NETSCAN_ROOT__#${ROOT}#g" \
      -e "s#__NETSCAN_USER__#$(id -un)#g" \
      scripts/netscan.service | sudo tee /etc/systemd/system/netscan.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now netscan.service
  sleep 2
  sudo systemctl --no-pager status netscan.service | head -6
fi

echo
echo "──────────────────────────────────────────────"
echo " Panel → http://$(hostname -I 2>/dev/null | awk '{print $1}'):1001"
[ "$WANT_SERVICE" = 1 ] || echo " Start it:  ./scripts/start.sh"
echo
echo " NetScan does not scan on its own — enrol an agent:"
echo "   Panel ▸ Config ▸ Agents ▸ New agent  (copy the token)"
if [ "$WANT_AGENT" = 1 ]; then
  echo "   ./scripts/install-agent-service.sh http://localhost:1001 <token>"
fi
echo "──────────────────────────────────────────────"
