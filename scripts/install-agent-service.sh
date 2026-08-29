#!/usr/bin/env bash
# Instala o agente NetScan como serviço systemd (arranca no boot, reinicia se
# falhar). Corre como o teu utilizador, com as capabilities de rede via systemd
# (raw sockets para o ARP/DHCP, sem setcap nem correr como root).
#
# Uso:  ./scripts/install-agent-service.sh <PANEL_URL> <ENROL_TOKEN> [NOME]
#   ex: ./scripts/install-agent-service.sh http://localhost:1001 poiXHef... raspi
#
# O token de inscrição é de uso único — obtém-o no painel em Config ▸ Agentes.
# Depois de inscrito, a chave fica em ~/.local/state/netscan-agent/agent.json e
# o token deixa de ser preciso.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PANEL_URL=${1:-http://localhost:1001}
ENROL_TOKEN=${2:-}
AGENT_NAME=${3:-$(hostname)}
STATE_FILE="$HOME/.local/state/netscan-agent/agent.json"

echo ">> A criar o venv do agente…"
python3 -m venv agent/.venv
agent/.venv/bin/pip -q install -r agent/requirements.txt
agent/.venv/bin/pip -q install ./protocol

echo ">> A escrever agent/.env"
cat > agent/.env <<EOF
NETSCAN_AGENT_PANEL_URL=${PANEL_URL}
NETSCAN_AGENT_NAME=${AGENT_NAME}
NETSCAN_AGENT_STATE_FILE=${STATE_FILE}
NETSCAN_AGENT_ENROL_TOKEN=${ENROL_TOKEN}
EOF
mkdir -p "$(dirname "$STATE_FILE")"

echo ">> A instalar /etc/systemd/system/netscan-agent.service"
sed -e "s#__NETSCAN_ROOT__#${ROOT}#g" \
    -e "s#__NETSCAN_USER__#$(id -un)#g" \
    scripts/netscan-agent.service | sudo tee /etc/systemd/system/netscan-agent.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now netscan-agent.service

echo
sudo systemctl --no-pager status netscan-agent.service | head -12
echo
echo "Saúde:  curl -s http://localhost:1002/health"
echo "Logs:   journalctl -u netscan-agent -f"
