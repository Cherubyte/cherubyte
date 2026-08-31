#!/usr/bin/env bash
# Instala o Cherubyte como serviço systemd (arranca no boot, reinicia se falhar).
# Corre como o teu utilizador, com as capabilities de rede via systemd
# (sem precisar de setcap em binários nem de correr como root).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo ">> A compilar o frontend…"
( cd frontend && npm install --no-audit --no-fund && npm run build )

echo ">> A instalar /etc/systemd/system/cherubyte.service"
sed -e "s#__CHERUBYTE_ROOT__#${ROOT}#g" \
    -e "s#__CHERUBYTE_USER__#$(id -un)#g" \
    scripts/cherubyte.service | sudo tee /etc/systemd/system/cherubyte.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now cherubyte.service

echo
sudo systemctl --no-pager status cherubyte.service | head -12
echo
echo "Pronto → http://$(hostname -I | awk '{print $1}'):1001"
echo "Logs:  journalctl -u cherubyte -f"
