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

0. **Reporta el inicio** del análisis para que la UI vea progreso:

   ```bash
   python hermes/skills/sapi-monitor/scripts/progress.py \
     --boletin-id <ID> --step analyzing_page \
     --current-page <1> --total-pages <total_pages>
   ```

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

   **A medida que avanzas**, actualiza el progreso tras cada página
   procesada (o al menos cada pocas páginas para no gastar pasos):
   ```bash
   python hermes/skills/sapi-monitor/scripts/progress.py \
     --boletin-id <ID> --step analyzing_page \
     --current-page <N_actual> --total-pages <total_pages>
   ```
   La UI mostrará "Hermes … página N de M". Si el análisis falla
   irrecuperablemente, reporta ``--step failed``.

3. Normaliza cada entrada al esquema `StructuredEntryIn`:

```json
{
  "expediente": "2015-015976",
  "marca": "TRIPLE MILLONARIO",
  "clase_niza": 35,
  "titular": "RAUL ENRIQUE ARTIGAS",
  "tramitante": "PEREZ & ASOCIADOS",
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
- `tramitante` es opcional (apoderado/agente que tramita). Inclúyelo
  solo si el boletín lo muestra; omítelo antes que inventarlo.
- `disposicion` (opcional): texto de la resolución SAPI que afecta a la
  marca cuando la entrada proviene de "Disposiciones Administrativas"
  (recursos, caducidad, revocaciones). Cita la parte de la decisión
  ("RESUELVE ..."), no el argumento legal completo.
- `tipo_disposicion` (opcional) ∈ `{NEGACION, CONCESION, CADUCA,
  REVOCA, INADMISIBLE, DEVOLUCION_FORMA, DEVOLUCION_FONDO}` según el
  efecto neto de la resolución sobre la marca. Omítelo si no queda
  claro.

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
- Fija `hermes_processed_at` y pone `hermes_progress_step='done'`, de modo
  que un boletín no se vuelve a procesar.

**No** calcules similitudes ni filtres por usuario desde la skill:
eso lo hace la API (SOUL.md: "no calculo similitud fonética/fuzzy").

### 4. Cierre del boletín (siempre)

Después de entregar las entries **o** si determinaste que el boletín **no
requiere visión** (texto confiable que el parser Python ya cubrió), cierra
el boletín para que salga de la cola y no quede pendiente para siempre:

```bash
python hermes/skills/sapi-monitor/scripts/done.py --boletin-id <ID> [--entries-added N]
```

- Si entregaste entries, pasa el número total con ``--entries-added``.
- Si fue un **no-op** (sin vision), cierra igual con ``done.py`` SIN
  entries: el endpoint fija ``hermes_processed_at`` + ``step='done'``.
- Idempotente: cerrar dos veces no crea duplicados. El propio
  ``submit.py`` ya marca ``hermes_processed_at``; ``done.py`` cubre el
  caso sin entries y sirve también de red de seguridad.

### 5. Verificación de conflictos (Fase 4)

El matcher Python auto-marca como candidatos las detecciones borderline:
marcas muy cortas (≤3 caracteres), confianza `medium`/`low`, o match por
familia de marca — las fuentes típicas de falsos positivos. TÚ las
confirmas o descartas en tu respuesta contra la decisión del motor. **No
calculas scores**: solo decides binario (`confirmed`/`discarded`) con un
motivo.

1. Lista la cola (solo lectura de SQLite):

   ```bash
   python hermes/skills/sapi-monitor/scripts/verify_queue.py [--db data/sapi.db] [--json]
   ```

2. Para cada candidato revisa el contexto (marca, `matched_with`, clase,
   similitud, excerpt, boletín). Si hace falta, abre la página con
   `extract_page.py` para ver el texto/imagen real.
3. Entrega el veredicto con `verify_submit.py`:

   ```bash
   python hermes/skills/sapi-monitor/scripts/verify_submit.py \
     --detection-id <ID> --verdict discarded \
     --reason "Marca 'X' de 1 carácter, no relacionada con '3XM'"
   ```

   - `confirmed`: el conflicto es real; se mantiene visible y sus alertas
     siguen activas.
   - `discarded`: falso positivo; la detección se oculta del listado
     accionable y sus alertas pendientes pasan a `descartada` (queda en BD
     para auditoría; un admin puede deshacer el veredicto).

El watchdog (`watchdog.sh`) ya incluye la cola de verificación (`V#...`),
así que el cron disparam solo cuando cambia también esa lista.

## Monitoreo periódico con cron (patrón watchdog)

Para que Hermes corra solo cuando hay trabajo nuevo, usa el cron con
`--monitor-script`:

```bash
# 1. Exponer el watchdog a Hermes.
#    IMPORTANTE: Hermes RECHAZA symlinks que escapen de ~/.hermes/scripts/
#    (validación de seguridad que resuelve link seguidos y exige que la
#    ruta quede dentro). Usa una COPIA ESTÁTICA; re-copiar tras cada pull
#    del watchdog en el repo.
cp "$PWD/hermes/skills/sapi-monitor/watchdog.sh" ~/.hermes/scripts/sapi_pending.sh
chmod +x ~/.hermes/scripts/sapi_pending.sh

# 2. Registrar el job recurrente. 'every 30m' = interval recurrente infinito
#    (Repeat=∞). Un '30m' sin "every" sería un disparo único (repeat=1).
hermes cron create 'every 30m' --name sapi-monitor \
  --monitor-script sapi_pending.sh \
  --skill sapi-monitor \
  --workdir /ruta/al/repo \
  --deliver local \
  "Procesa los boletines SAPI pendientes de revisión visual."

# 3. El scheduler lo maneja el gateway de Hermes. Para ejecución automática
#    persistente en un servidor (Ubuntu/systemd):
hermes gateway install          # servicio de usuario (sin sudo)
hermes cron status              # debe decir "cron jobs will fire automatically"
```

> Nota 1: `--deliver local` entrega el resultado en la salida local.
> No configures `telegram:...`/`discord:...` hasta que esa plataforma
> esté habilitada en `hermes status`; de lo contrario el delivery fallará.

> Nota 2: el watchdog (`watchdog.sh`) es estable — no imprime timestamps
> ni recuentos totales variables — para que el `--monitor-script` solo
> dispare cuando haya trabajo nuevo y no gaste tokens cada tick. Al
> copiarlo estáticamente, re-cópialo si lo editas en el repo.

El `--monitor-script` devuelve la lista de pendientes; si no cambió
respecto a la última vez, Hermes no corre (ahorra tokens). Cuando
cambia, se inyecta el diff y la skill hace el flujo completo.

## Notas operativas

- **Solo lectura en SQLite**: importa rutas de la BD, pero jamás la
  modifiques. Cualquier escritura va por la API.
- **Siempre respeta el límite**: el endpoint acepta hasta 100 entries
  por request; usa `submit.chunk_entries` si tienes más.
- **Idioma**: las entradas, documentos y prompts, en español.
