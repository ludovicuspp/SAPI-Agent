#!/usr/bin/env bash
# Runbook de bootstrap para el CD de SAPI-Agent.
# EJECUTAR EN UNA TTY INTERACTIVA con sudo (pide password una vez).
set -euo pipefail

SERVICE_FILE=/etc/systemd/system/sapi-api.service
SUDOERS_FILE=/etc/sudoers.d/sapi-api-restart

echo "=== [1/5] Comprobando prerequisites ==="
test -d /home/luisv/SAPI-Agent || { echo "repo no clonado"; exit 1; }
test -x /home/luisv/.local/bin/uvicorn || { echo "uvicorn no instalado en /home/luisv/.local"; exit 1; }

echo "=== [2/5] Creando /etc/systemd/system/sapi-api.service ==="
sudo tee "$SERVICE_FILE" >/dev/null <<'EOF'
[Unit]
Description=SAPI-Agent API (FastAPI)
After=network.target

[Service]
Type=simple
User=luisv
WorkingDirectory=/home/luisv/SAPI-Agent
EnvironmentFile=/home/luisv/SAPI-Agent/.env
ExecStart=/home/luisv/.local/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "=== [3/5] Permitiendo a luisv reiniciar sapi-api sin password ==="
sudo tee "$SUDOERS_FILE" >/dev/null <<'EOF'
luisv ALL=(root) NOPASSWD: /usr/bin/systemctl restart sapi-api.service
luisv ALL=(root) NOPASSWD: /usr/bin/systemctl is-active sapi-api.service
EOF
sudo chmod 440 "$SUDOERS_FILE"
sudo visudo -c -f "$SUDOERS_FILE"

echo "=== [4/5] Parando uvicorn ad-hoc y arrancando sapi-api ==="
pkill -f "[u]vicorn" || true
sleep 1
sudo systemctl daemon-reload
sudo systemctl enable sapi-api.service
sudo systemctl start sapi-api.service
sleep 2
sudo systemctl is-active sapi-api.service
echo "--- health local ---"
curl -sf http://127.0.0.1:8000/api/health || { echo "FALLO health"; exit 1; }

echo "=== [5/5] Verificando sudo -n NOPASSWD ==="
sudo -n systemctl is-active sapi-api.service && echo "sudo -n OK"

echo "=== LISTO. La VM esta lista para el CD. ==="
echo "Proximo paso manual:"
echo "  1) Regenerar tu PAT con scope 'workflow' (o crear uno nuevo en GitHub)."
echo "  2) git push origin main"
echo "  3) Subir Secrets (SSH_HOST=216.106.180.48, SSH_USER=luisv, SSH_PORT=22,"
echo "     SSH_PRIVATE_KEY=contenido de ~/.ssh/id_ed25519_sapi_cicd) en la UI:"
echo "       https://github.com/ludovicuspp/SAPI-Agent/settings/secrets/actions"
