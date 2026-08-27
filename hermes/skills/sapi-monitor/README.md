# sapi-monitor

Skill de Hermes para la **revisión visual** de los boletines SAPI que
el parser de texto no pudo procesar por completo (páginas escaneadas
con imágenes o con encoding `cid:` roto).

## Qué hace

1. Detecta en la BD los boletines con `needs_hermes_review=1` y sin
   `hermes_processed_at`.
2. Para cada boletín, el LLM (Hermes) decide por página si:
   - se salta (texto confiable ya cubierto por el parser),
   - normaliza el texto con un prompt (más barato),
   - usa visión multimodal sobre un render PNG de la página.
3. Entrega las entradas estructuradas a la API
   (`POST /api/boletines/{id}/structured`), que calcula los matches
   en Python y persiste las detecciones.

La skill **solo lee** la base, nunca la escribe, y **no calcula
similitudes** (eso es de Python).

## Scripts

| Script | Función |
|---|---|
| `scripts/pending_boletines.py` | Lista boletines pendientes (también usable como watchdog de cron) |
| `scripts/db_utils.py` | Acceso read-only a `data/sapi.db` |
| `scripts/extract_page.py` | Texto de una página o render a PNG |
| `scripts/submit.py` | POST de entries a la API (con `X-Hermes-Token`) |

Se invocan como **archivos** (no como paquete; el directorio lleva
guion). Cada script hace bootstrap de `sys.path` para importar
`scripts.*` del repo.

## Requisitos

- API corriendo (`HERMES_API_URL`, default `http://localhost:8000`).
- `SERVICE_TOKEN_HERMES` en el entorno (o `.env` del repo).
- `data/sapi.db` con el esquema de `scripts/db.py`.
- Dependencias del repo (`requirements.txt`): pdfplumber, pymupdf,
  httpx, etc.

## Probar

```bash
# Verpendientes
python hermes/skills/sapi-monitor/scripts/pending_boletines.py --db data/sapi.db

# Tests
pytest hermes/skills/sapi-monitor/tests -v
```

## Cron (watchdog)

Ver la sección "Monitoreo periódico con cron" en `SKILL.md`. El patrón
recomendado es una **copia estática** del watchdog (Hermes rechaza
symlinks que escapen de `~/.hermes/scripts/`) y un job **recurrente**:

```bash
cp "$PWD/hermes/skills/sapi-monitor/watchdog.sh" ~/.hermes/scripts/sapi_pending.sh
chmod +x ~/.hermes/scripts/sapi_pending.sh
hermes cron create 'every 30m' --name sapi-monitor \
  --monitor-script sapi_pending.sh \
  --skill sapi-monitor \
  --workdir /ruta/al/repo \
  --deliver local \
  "Procesa los boletines SAPI pendientes de revisión visual."
```

`'every 30m'` (con "every") = recurrente infinito; `'30m'` solo = un
disparo único. El `--monitor-script` solo dispara al agente cuando
cambia el output del watchdog, así que ahorra tokens. La ejecución
automática corre bajo el gateway de Hermes (`hermes gateway install`).

## Convenciones

- Documentación y prompts en **español**.
- `fuente` ∈ `{hermes_llm, hermes_vision}`; `confianza` ∈ `{high,
  medium, low}` (los sets que ya valida la API).
- No inventar expedientes/marcas/titulares que no sean legibles.
