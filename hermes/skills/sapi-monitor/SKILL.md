---
name: sapi-monitor
description: "Procesa los boletines SAPI Venezuela pendientes de revisión visual (needs_hermes_review=1). Para cada página, TÚ (el LLM) decides si basta el texto o si hace falta visión multimodal, y entregas las entradas estructuradas a la API vía POST /api/boletines/{id}/structured."
version: 0.1.0
author: Luis Vargas
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [SAPI, Venezuela, Marcas, Boletines, PDF, Vision, Propiedad-Intelectual, Monitoring]
    related_skills: [nano-pdf, pdf]
prerequisites:
  env_vars: [SERVICE_TOKEN_HERMES, HERMES_API_URL]
  files: [data/sapi.db]
---

# sapi-monitor

Orquesta la **fase de revisión visual** de los boletines SAPI. Es un
orquestador, no un ejecutor: tú decides qué páginas requieren visión,
normalizas las entradas con el LLM y las entregas a la API para que
Python calcule los match scores y persista.

## Cuándo usar

- "Procesa los boletines pendientes de revisión visual."
- "¿Hay boletines por revisar con Hermes?"
- Lo invoca el cron de forma periódica (watchdog).

**No** usar para: parsing de texto ya confiable (lo hace el parser
Python), ni para calcular similitudes (siempre Python vía la API).

## Prerequisitos

- La API corriendo y accesible en `HERMES_API_URL` (default
  `http://localhost:8000`).
- `SERVICE_TOKEN_HERMES` configurado en el entorno / `.env`. Sin él,
  los POST a la API devuelven 503/403.
- `data/sapi.db` existente (esquema de `scripts/db.py`).

## Flujo

### 1. Detectar pendientes

```bash
python hermes/skills/sapi-monitor/scripts/pending_boletines.py --db data/sapi.db
```

Esto lista los boletines con `needs_hermes_review=1` aún sin
`hermes_processed_at`, y reporta por boletín cuántas páginas tienen
imágenes y cuántas tienen texto de baja confianza.

**Defensa de duplicados**: el endpoint ignora boletines ya procesados
(devuelve `status=already_processed`), así que no hace falta comprobar
antes de enviar.

### 2. Por cada boletín pendiente

1. Lee el `extraction_json` (páginas con `has_images` y
   `low_confidence`) que dejó el parser en la BD:
   ```bash
   python hermes/skills/sapi-monitor/scripts/extract_page.py --help
   ```
2. Para cada página, **TÚ decides** (LLM, leyendo la página):
   - **Texto confiable** y sin imágenes → **SKIP**. El parser Python
     ya cubrió esa entrada; no la reenvíes.
   - **Texto parcial / orden raro pero legible** → usa el texto
     directamente (extrae con `extract_page.page_text`) y normaliza
     con un prompt de extracción (más barato que visión).
   - **Imagen embebida / encoding `cid:` roto / texto vacío** →
     renderiza la página a PNG y usa **visión multimodal**:
     ```bash
     python hermes/skills/sapi-monitor/scripts/extract_page.py --pdf <file_path> --page N --render <tmp_dir>
     ```
     y luego analízala con tu canal de visión sobre el PNG generado.
3. Normaliza cada entrada al esquema `StructuredEntryIn`:

```json
{
  "expediente": "2015-015976",
  "marca": "TRIPLE MILLONARIO",
  "clase_niza": 35,
  "titular": "RAUL ENRIQUE ARTIGAS",
  "pais": "VENEZUELA",
  "estatus": "PUBLICADA",
  "pagina": 8,
  "fuente": "hermes_vision",
  "confianza": "high",
  "excerpt": "Insc. 2015-015976 del 30 DE OCTUBRE DE 2015 SOLICITADA POR: ..."
}
```

Reglas del esquema (NO inventes valores fuera de estos conjuntos):

- `fuente` ∈ `{hermes_llm, hermes_vision}`. Usa `hermes_llm` cuando
  normalizaste texto limpio y `hermes_vision` cuando leíste de una
  imagen.
- `confianza` ∈ `{high, medium, low}` según claridad visual del dato.
- `estatus` se normaliza a MAYÚSCULAS (ej. `PUBLICADA`, `CONCEDIDA`,
  `NEGADA`).
- `clase_niza` ∈ [1, 45]. El lema comercial va con `clase_niza` que
  refleje su clase real si es identificable; si no, usa 0→NO (evita
  inventar). Mejor omitir la entrada que inventar un dato.
- `expediente`, `marca` y `titular` son obligatorios; si no son
  identificables, no envíes esa entrada.

### 3. Entregar a la API

```bash
export HERMES_API_URL=http://localhost:8000
export SERVICE_TOKEN_HERMES=<tu-token>
python hermes/skills/sapi-monitor/scripts/submit.py \
  --boletin-id <ID> --entries <entries.json> \
  [--api-url ...] [--token ...]
```

O, desde Python, construye `list[StructuredEntry]` y llama a
`submit.submit(boletin_id, entries)`.

El endpoint:
- Calcula la similitud contra **todas** las watchlists activas
  (multi-tenant) y contra los portafolios por expediente.
- Crea las `detections` correspondientes.
- Fija `hermes_processed_at`, de modo que un boletín no se vuelve a
  procesar.

**No** calcules similitudes ni filtres por usuario desde la skill:
eso lo hace la API (SOUL.md: "no calculo similitud fonética/fuzzy").

## Monitoreo periódico con cron (patrón watchdog)

Para que Hermes corra solo cuando hay trabajo nuevo, usa el cron con
`--monitor-script`:

```bash
# 1. Exponer el watchdog del repo a Hermes (enlace simbólico):
ln -sf "$PWD/hermes/skills/sapi-monitor/watchdog.sh" ~/.hermes/scripts/sapi_pending.sh

# 2. Registrar el job (corre cada 30m, solo dispara al agente si cambió):
hermes cron create '30m' --name sapi-monitor \
  --monitor-script sapi_pending.sh \
  --skill sapi-monitor \
  --workdir /ruta/al/repo \
  "Procesa los boletines SAPI pendientes de revisión visual."
```

> Nota: el watchdog (`watchdog.sh`) es estable — no imprime timestamps
> ni recuentos totales variables — para que el `--monitor-script` solo
> dispare cuando haya trabajo nuevo y no gaste tokens cada tick.

El `--monitor-script` devuelve la lista de pendientes; si no cambió
respecto a la última vez, Hermes no corre (ahorra tokens). Cuando
cambia, se inyecta el diff y la skill hace el flujo completo.

## Notas operativas

- **Solo lectura en SQLite**: importa rutas de la BD, pero jamás la
  modifiques. Cualquier escritura va por la API.
- **Siempre respeta el límite**: el endpoint acepta hasta 100 entries
  por request; usa `submit.chunk_entries` si tienes más.
- **Idioma**: las entradas, documentos y prompts, en español.
