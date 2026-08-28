# 01 — Requisitos funcionales

Cada requisito tiene un ID (`RF-NN`), prioridad (`Alta/Media/Baja`),
descripción y estado de implementación.

## Leyenda de estado

| Marca | Significado |
|---|---|
| ✅ | Implementado y verificado por tests |
| 🟡 | Implementado parcialmente; falta cobertura o casos borde |
| ⬜ | Pendiente; no implementado |
| 🚫 | Descartado (ver nota) |

## Tabla de requisitos

| ID | Requisito | Prioridad | Estado | Verificación |
|---|---|---|---|---|
| RF-01 | Subir PDF de boletín vía `/api/boletines/upload` (multipart, `MAX_UPLOAD_MB=300`) | Alta | ✅ | `tests/test_api.py::test_upload_*` |
| RF-02 | Extracción automática con `pdfplumber` y fallback `pymupdf` (encoding cid:NNN) | Alta | ✅ | `tests/test_processor.py` |
| RF-03 | Estructuración por patrones A/B/C (`scripts/parsers/marca_entry.py`) | Alta | ✅ | `tests/test_patterns.py`, `tests/test_parsers.py` |
| RF-04 | Revisión visual con Hermes (LLM multimodal) para páginas con `has_images` o `low_confidence` | Alta | ✅ | `tests/test_orquestador.py`, `tests/test_pipeline_e2e.py::test_e2e_hermes_vision_si_necesario` |
| RF-05 | Motor de similitud: exacto + fuzzy (rapidfuzz) + fonético (jellyfish) + combinado | Alta | ✅ | `tests/test_matchers.py`, `tests/test_matcher_calidad.py` |
| RF-06 | Notificación por email de nuevas detecciones (SMTP, cooldown 24 h) | Alta | ✅ | `scripts/notifiers/email_smtp.py`, `tests/test_processor.py::TestNotifierMocked` |
| RF-07 | Dashboard React: login, summary, boletines, detecciones, watchlist, portfolio, users | Alta | ✅ | `dashboard/src/pages/*` (32 tests Vitest) |
| RF-08 | CRUD de watchlist por usuario (multi-tenant) | Alta | ✅ | `api/routers/watchlist.py`, `tests/test_api.py` |
| RF-09 | CRUD de portfolio por usuario | Alta | ✅ | `api/routers/portfolio.py`, `tests/test_api.py` |
| RF-10 | Multi-tenancy: `watchlist`, `portfolio`, `boletines`, `detections` filtrados por `user_id` | Alta | ✅ | `scripts/db.py`, `api/deps.py::get_current_user` |
| RF-11 | Autenticación JWT (HS256, 8 h expiry, header `Authorization: Bearer`) | Alta | ✅ | `scripts/auth.py`, `tests/test_auth.py` |
| RF-12 | WebSocket de progreso de procesamiento por boletín | Media | ✅ | `api/routers/uploads.py::ws_progress` |
| RF-13 | Idempotencia de Hermes: defensa contra duplicados vía `hermes_processed_at` | Alta | ✅ | `tests/test_orquestador.py::test_orq_structured_idempotente` |
| RF-14 | Dedupe de detecciones por `(boletin_id, expediente, watchlist_id)` | Alta | ✅ | `scripts/db.py::idx_detections_dedupe`, `INSERT OR IGNORE` |
| RF-15 | Cap top-5 matches por entry de Hermes (anti-alucinación) | Alta | ✅ | `api/routers/structured.py::_MAX_MATCHES_PER_ENTRY`, `tests/test_orquestador.py::test_orq_structured_cap_top5` |
| RF-16 | Validación de `estatus` contra `EstatusLiteral` (10 valores SAPI) | Alta | ✅ | `scripts/schemas.py`, `tests/test_alucinaciones.py` |
| RF-17 | Background task para procesar PDF sin bloquear el upload | Alta | ✅ | `api/routers/uploads.py::_process_boletin_task` |
| RF-18 | Logging estructurado en `scans_log` (upload/extract/hermes/notify/match) | Media | ✅ | `scripts/db.py::scans_log_record` |
| RF-19 | `CLI` para operaciones admin: `init-db`, `create-user`, `add-watchlist`, `send-digest`, `stats` | Media | ✅ | `scripts/cli.py` |
| RF-20 | Módulo de monitoreo en dashboard con métricas (processing time, error rate, etc.) | Media | ⬜ | pendiente — Rama F del grill |
| RF-21 | Ajuste de umbrales de matching por usuario (override de defaults) | Media | ⬜ | pendiente — Rama G del grill |
| RF-22 | Carga de boletín desde dashboard (botón + progreso WebSocket) | Alta | 🟡 | UI existe; probar carga real — Rama C |
| RF-23 | Notificación email de fallos del `pull_deploy.sh` a 2 destinatarios | Baja | ⬜ | bloqueado por SMTP sin credenciales |
| RF-24 | Revisión por Hermes Vision de detecciones con sospecha de falso positivo | Baja | ⬜ | pendiente — Rama G del grill |
| RF-25 | Versionado de API: prefijo `/api/v0/` (sustituye `/api/` actual) | Baja | ⬜ | Rama H del grill |
| RF-26 | Soporte para múltiples canales de notificación (Slack, push, SMS) | Baja | 🚫 | descartado por Rama H — solo email |
| RF-27 | Soporte de idiomas distintos al español | Baja | 🚫 | descartado por Rama H — solo español |
| RF-28 | Automatización de login en WEBPI (reCAPTCHA v3) | Baja | 🚫 | bloqueado por WEBPI + reCAPTCHA |
| RF-29 | Scraping de `sapi.gob.ve` para descarga automática | Baja | 🚫 | boletines los suben usuarios |
| RF-30 | Cálculo de similitud en el LLM (en lugar de Python) | Alta | 🚫 | violaría principio: similitud siempre Python |

## Notas

- **RF-15 y RF-16** surgieron de la fase de pruebas como protección
  contra alucinaciones del LLM.
- **RF-23** depende de configurar `SMTP_USER` y `SMTP_PASSWORD` reales
  en `.env`. Mientras estén vacíos, el notifier degrada a log silencioso.
- **RF-24** complementa RF-15: si el usuario sospecha falso positivo,
  dispara una verificación visual con Hermes.
- **RF-30** es una **decisión arquitectónica explícita**: el LLM
  solo extrae campos, NUNCA calcula similitud (regla en `AGENTS.md`).