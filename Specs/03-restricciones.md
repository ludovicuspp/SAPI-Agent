# 03 — Restricciones y supuestos

## Restricciones externas

### R-EXT-01 — WEBPI no automatizable

- **WEBPI** (consulta de expedientes del SAPI Venezuela) requiere
  login + **reCAPTCHA v3**.
- **No** automatizamos el login.
- **No** scrapeamos `sapi.gob.ve`.
- **Horario** WEBPI: 8:00 AM – 11:30 PM hora Venezuela.
- **Implicación:** la consulta de estatus de expedientes propios se
  nutre de los boletines que los usuarios suben al sistema.

### R-EXT-02 — SAPI.gob.ve sin scraping

- Los boletines se suben manualmente por los usuarios a través del
  dashboard.
- No hay automatización de descarga desde el sitio público del SAPI.

### R-EXT-03 — SMTP del operador

- Las notificaciones usan SMTP genérico (cualquier proveedor:
  SendGrid, Mailgun, Gmail, AWS SES).
- Mientras `SMTP_USER`/`SMTP_PASSWORD` estén vacíos en `.env`, el
  notifier degrada a **log silencioso** (no rompe el script).
- Destinatarios planeados para alertas de fallo y de detección:
  - `luis.vargas@ironflexgroup.com`
  - `tecnologia@inversionesterraplena.com`

### R-EXT-04 — TLS / Caddy externo

- La VM tiene **IP privada** (`10.10.10.228`) y una IP pública
  (`216.106.180.246`).
- El puerto 22 responde un servidor SSH del proveedor, **no** la VM.
- El Caddy externo del proveedor maneja TLS y reverse proxy a la API.
- El unit `sapi-api.service` bind a `127.0.0.1:8000`; Caddy hace
  proxy_pass al loopback de la VM.

## Restricciones técnicas

### R-TEC-01 — Python 3.14 y dependencias nativas

- Runtime en VM: **Python 3.14.4**.
- Algunas wheels (`pymupdf`, `aiosmtplib`) requieren compilación en
  versiones muy nuevas; CI usa **Python 3.12 LTS** para evitar fallos.
- `httpx2` (paquete real, no typo) está pinneado en `requirements-dev.txt`.

### R-TEC-02 — SQLite como BD

- BD embebida (`data/sapi.db`).
- **Una sola capa de escritura:** CLI y API escriben vía
  `scripts/db.py`. Hermes y la skill `sapi-monitor` **solo leen**.
- Escritura desde Hermes siempre vía
  `POST /api/boletines/{id}/structured`.
- `check_same_thread=False` activado para FastAPI threadpool.
- FK activadas con `PRAGMA foreign_keys = ON`.

### R-TEC-03 — Enums de valores (no inventar)

Estos campos tienen valores literales **fijos**, definidos en
`scripts/schemas.py`. **No** añadir valores nuevos sin actualizar
`scripts/schemas.py` y añadir un test en `tests/test_alucinaciones.py`.

| Campo | Valores permitidos |
|---|---|
| `role` | `admin`, `agent` |
| `match_kind` | `similar`, `own_status` |
| `source` | `pdfplumber_text`, `hermes_llm`, `hermes_vision` |
| `confidence` | `high`, `medium`, `low` |
| `estatus` | `PUBLICADA`, `CONCEDIDA`, `NEGADA`, `DESISTIDA`, `OPOSICION`, `PRORROGADA`, `CADUCA`, `EN_TRAMITE`, `PRIMERA_PUBLICACION`, `SEGUNDA_PUBLICACION` |

### R-TEC-04 — Umbrales de matching (defaults globales)

- `match_threshold = 85` (no usado directamente; reservado).
- `fuzzy_threshold = 80` (rapidfuzz WRatio ≥ 80 → match).
- `phonetic_threshold = 0.75` (jellyfish, no usado en `combined.py`
  hoy; fonético idéntico → match con similarity=0.70).

`scripts/config.py:42-44`.

### R-TEC-05 — Cooldown de notificaciones

- `NOTIFY_COOLDOWN_HOURS = 24`. Una misma detection no se reenvía
  por email antes de 24 h.

## Supuestos

- **S-01**: el usuario es el único que sube boletines (no hay un
  cron que descargue de sapi.gob.ve).
- **S-02**: hay al menos un usuario `admin` sembrado por
  `init-db` si `ADMIN_EMAIL` y `ADMIN_PASSWORD` están en `.env`.
- **S-03**: la BD es local; el sistema es **single-node** (sin
  replicación).
- **S-04**: el dashboard y la API están en el mismo host; no hay
  separación de origen cross-domain en producción (CORS solo permite
  el dominio público configurado).
- **S-05**: los boletines están en español (Boletín de la Propiedad
  Industrial de Venezuela).
- **S-06**: el usuario tiene Linger=yes para user systemd (sapi-pull.timer).

## Dependencias externas

| Componente | Versión / Rango | Fuente |
|---|---|---|
| Python | 3.14 (runtime), 3.12 (CI) | `scripts/config.py`, `.github/workflows/ci.yml` |
| Node | 22 LTS (CI), 26 (runtime VM) | `dashboard/package.json` |
| React | 19.x | `dashboard/package.json` |
| FastAPI | ≥0.115 | `requirements.txt` |
| pdfplumber | ≥0.11 | `requirements.txt` |
| pymupdf | ≥1.24 | `requirements.txt` |
| rapidfuzz | ≥3.10 | `requirements.txt` |
| jellyfish | ≥1.0 | `requirements.txt` |
| bcrypt | (vía passlib[bcrypt]) | `requirements.txt` |
| pytest | ≥8.0 | `requirements-dev.txt` |
| Vitest | ≥2.1.8 | `dashboard/package.json` |