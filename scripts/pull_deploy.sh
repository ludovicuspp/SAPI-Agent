#!/usr/bin/env bash
# Pull-based deploy: trae el último commit de main y reconstruye si hay cambios.
# Diseñado para ejecutarse desde un systemd timer (sapi-pull.timer).
#
# Comportamiento:
#  1) git fetch + rev-parse para comparar local vs origin/main
#  2) Si hay cambios (HEAD local != origin/main), hace git pull --ff-only
#  3) Reconstruye el dashboard (npm ci --omit=dev && npm run build)
#  4) pip install -r requirements.txt (idempotente)
#  5) Reinicia sapi-api.service via sudo -n (requiere NOPASSWD)
#  6) Health-check local (curl 127.0.0.1:8000)
set -euo pipefail

REPO_DIR="/home/luisv/SAPI-Agent"
LOG_FILE="/home/luisv/data/sapi-pull.log"
LOCK_FILE="/home/luisv/data/sapi-pull.lock"

mkdir -p "$(dirname "$LOG_FILE")"
exec >> "$LOG_FILE" 2>&1

echo "=========================================="
echo "[$(date -u +%FT%TZ)] sapi-pull: start"

# Lock para evitar carreras si dos timers disparan a la vez.
if [ -e "$LOCK_FILE" ]; then
  echo "Lock existente ($LOCK_FILE); saliendo."
  exit 0
fi
trap 'rm -f "$LOCK_FILE"' EXIT
echo $$ > "$LOCK_FILE"

cd "$REPO_DIR"

LOCAL_HEAD=$(git rev-parse HEAD)
git fetch --quiet origin main
REMOTE_HEAD=$(git rev-parse origin/main)

echo "local=$LOCAL_HEAD remote=$REMOTE_HEAD"

if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
  echo "Sin cambios; nada que desplegar."
  exit 0
fi

echo "Cambios detectados. Aplicando git pull --ff-only..."
git pull --ff-only

# Backend deps (idempotente, rápido si no cambian)
python -m pip install -q -r requirements.txt

# Dashboard build (rebuild con .env.production que ya viene en el repo)
cd dashboard
npm ci --omit=dev --silent
npm run build --silent
cd ..

# Reiniciar servicio gestionado
echo "Reiniciando sapi-api.service..."
sudo -n systemctl restart sapi-api.service
sleep 2

# Health-check local
if curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
  echo "Health OK"
else
  echo "Health FAIL; ver journalctl"
  sudo -n journalctl -u sapi-api.service -n 30 --no-pager || true
  exit 1
fi

echo "[$(date -u +%FT%TZ)] sapi-pull: done"
