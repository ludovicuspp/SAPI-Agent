#!/bin/bash
# Watchdog para el cron de Hermes: lista boletines pendientes de revisión
# visual. Su stdout debe ser ESTABLE (sin timestamps) para que Hermes
# compare por hash y solo dispare al agente cuando cambie la lista.
#
# Se invoca desde el cron de Hermes vía --monitor-script. Requiere
# copiarse/enlazarse a ~/.hermes/scripts/sapi_pending.sh (ver SKILL.md).
#
# Uso directo:
#   bash hermes/skills/sapi-monitor/watchdog.sh /ruta/al/repo
set -euo pipefail

REPO_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
DB="$REPO_DIR/data/sapi.db"

if [[ ! -f "$DB" ]]; then
    echo "SIN_PENDIENTES"
    exit 0
fi

cd "$REPO_DIR"

# Lista pendientes estable: EXCLUDE la cuenta total (varía) y el campo pages
# variable; emitimos solo los ids con su marca de "necesita revisión".
python3 hermes/skills/sapi-monitor/scripts/pending_boletines.py --db "$DB" --json \
  | python3 -c '
import sys, json
data = json.load(sys.stdin)
if not data:
    print("SIN_PENDIENTES")
else:
    for b in data:
        # Solo la parte relevante para detectar cambio de trabajo nuevo.
        print(f"#{b[\"boletin_id\"]} {b[\"filename\"]} imgs={b[\"pages_with_images\"]}")
'
