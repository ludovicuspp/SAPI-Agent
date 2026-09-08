#!/usr/bin/env bash
# Pull-based deploy: trae el último commit de main y reconstruye si el
# código desplegado quedó atrás. Diseñado para un systemd timer
# (sapi-pull.timer).
#
# Por qué un MARCADOR y no "local vs origin/main":
#   En esta VM el checkout de desarrollo y el de producción son el MISMO
#   (/home/luisv/SAPI-Agent). Al hacer `git push` desde aquí, HEAD local
#   ya avanza a origin/main al instante, así que comparar local==remote
#   daba SIEMPRE "sin cambios" y el build+restart NUNCA corría: el
#   servicio se quedaba con código viejo en memoria (ver incidente del
#   módulo Resumen: DetectionRow sin `risk_score`).
#
#   La verdad operativa es "¿qué commit está REALMENTE desplegado?".
#   Eso se guarda en DEPLOYED_MARKER y se compara contra HEAD tras el
#   fetch+pull. El marcador solo se actualiza si el deploy termina OK.
#
# Comportamiento:
#  1) git fetch + pull --ff-only (por si algún día los commits llegan de
#     otra máquina; en esta VM es no-op inofensivo)
#  2) Compara HEAD contra el marcador del último deploy exitoso
#  3) Si difieren (o no hay marcador): pip install, build dashboard,
#     restart sapi-api.service, health-check
#  4) Solo si el health pasa, escribe el marcador con el HEAD desplegado
set -euo pipefail

# El systemd user service arranca con un PATH mínimo; node/npm/pip3 viven
# en ~/.local/bin. Forzamos el PATH para que el build no falle con
# "command not found" al dispararse desde el timer.
export PATH="/home/luisv/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_DIR="/home/luisv/SAPI-Agent"
LOG_FILE="/var/log/sapi-pull.log"
LOCK_FILE="/home/luisv/data/sapi-pull.lock"
DEPLOYED_MARKER="/home/luisv/data/sapi-deployed-head"

mkdir -p "$(dirname "$LOCK_FILE")"
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

# Traer y aplicar lo remoto (no-op si ya estamos al día).
git fetch --quiet origin main
git pull --ff-only --quiet || true

HEAD_NOW=$(git rev-parse HEAD)
DEPLOYED=""
if [ -f "$DEPLOYED_MARKER" ]; then
  DEPLOYED=$(cat "$DEPLOYED_MARKER" 2>/dev/null || true)
fi

echo "head=$HEAD_NOW deployed=${DEPLOYED:-<ninguno>}"

if [ "$HEAD_NOW" = "$DEPLOYED" ]; then
  echo "Ya desplegado; nada que hacer."
  exit 0
fi

echo "Desplegando $HEAD_NOW ..."

# Backend deps (idempotente, rápido si no cambian)
python3 -m pip install -q -r requirements.txt

# Dashboard build (rebuild con .env.production que ya viene en el repo)
cd dashboard
npm ci --omit=dev --silent
npm run build --silent
cd ..

# Reiniciar servicio gestionado
echo "Reiniciando sapi-api.service..."
sudo -n systemctl restart sapi-api.service
sleep 2

# Health-check local: solo si pasa marcamos el deploy como bueno.
if curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
  echo "Health OK"
  echo "$HEAD_NOW" > "$DEPLOYED_MARKER"
  echo "[$(date -u +%FT%TZ)] sapi-pull: done ($HEAD_NOW)"
else
  echo "Health FAIL; ver journalctl (marcador NO actualizado)"
  sudo -n journalctl -u sapi-api.service -n 30 --no-pager || true
  exit 1
fi
