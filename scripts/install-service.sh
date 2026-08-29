#!/usr/bin/env bash
# Instala o NetScan como serviço systemd (arranca no boot, reinicia se falhar).
# Corre como o teu utilizador, com as capabilities de rede via systemd
# (sem precisar de setcap em binários nem de correr como root).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo ">> A compilar o frontend…"
( cd frontend && npm install --no-audit --no-fund && npm run build )

echo ">> A instalar /etc/systemd/system/netscan.service"
sed -e "s#__NETSCAN_ROOT__#${ROOT}#g" \
    -e "s#__NETSCAN_USER__#$(id -un)#g" \
    scripts/netscan.service | sudo tee /etc/systemd/system/netscan.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now netscan.service

echo
sudo systemctl --no-pager status netscan.service | head -12
echo
echo "Pronto → http://$(hostname -I | awk '{print $1}'):1001"
echo "Logs:  journalctl -u netscan -f"
