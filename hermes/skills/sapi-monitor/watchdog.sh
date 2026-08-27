#!/bin/bash
# Watchdog para el cron de Hermes: lista boletines pendientes de revisión
# visual. Su stdout debe ser ESTABLE (sin timestamps) para que Hermes
# compare por hash y solo dispare al agente cuando cambie la lista.
#
# Se invoca desde el cron de Hermes vía --monitor-script. Hermes NO
# permite symlinks que escapen de ~/.hermes/scripts/, así que este
# script se COPIA a ~/.hermes/scripts/sapi_pending.sh. La raíz del repo
# se resuelve de forma robusta (ver _resolve_repo).
#
# Uso directo:
#   bash hermes/skills/sapi-monitor/watchdog.sh [REPO_DIR]
set -euo pipefail

# 1) Argumento explícito (útil en pruebas directas).
REPO_DIR="${1:-}"

# 2) Env override (útil para el cron).
if [[ -z "$REPO_DIR" && -n "${SAPI_REPO_DIR:-}" ]]; then
    REPO_DIR="$SAPI_REPO_DIR"
fi

# 3) Si cwd contiene data/sapi.db, es la raíz del repo (el cron usa --workdir).
if [[ -z "$REPO_DIR" && -f "$PWD/data/sapi.db" ]]; then
    REPO_DIR="$PWD"
fi

# 4) Fallback: 4 niveles arriba de este script (si se ejecuta en el repo)
#    o 3 niveles arriba si es una copia en ~/.hermes/scripts/.
if [[ -z "$REPO_DIR" ]]; then
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    case "$HERE" in
        *SAPI-Agent/hermes/skills/sapi-monitor/scripts)
            REPO_DIR="$(cd "$HERE/../../../.." && pwd)"
            ;;
        */.hermes/scripts)
            REPO_DIR="$(cd "$HERE/../.." && pwd)"
            # La copia en ~/.hermes/scripts no sabe dónde está el repo;
            # requerimos env o workdir.
            REPO_DIR=""
            ;;
        *)
            REPO_DIR="$(cd "$HERE/../../../.." && pwd)"
            ;;
    esac
fi

DB="$REPO_DIR/data/sapi.db"

if [[ -z "$REPO_DIR" || ! -f "$DB" ]]; then
    echo "SIN_PENDIENTES"
    exit 0
fi

cd "$REPO_DIR"

# Lista pendientes estable: emitimos solo los ids con su marca de
# "necesita revisión" (sin recuentos totales que variarían cada tick).
python3 hermes/skills/sapi-monitor/scripts/pending_boletines.py --db "$DB" --json \
  | python3 -c '
import sys, json
data = json.load(sys.stdin)
if not data:
    print("SIN_PENDIENTES")
else:
    for b in data:
        print("#%s %s imgs=%s" % (b["boletin_id"], b["filename"], b["pages_with_images"]))
'
