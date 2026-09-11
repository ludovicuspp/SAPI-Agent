# 02 — Requisitos no funcionales

Requisitos transversales de calidad, seguridad, rendimiento y
mantenibilidad. Mismo formato que `01-requisitos.md`.

| ID | Requisito | Categoría | Estado | Verificación |
|---|---|---|---|---|
| RNF-01 | Latencia de procesamiento del boletín < 15 min (objetivo de negocio) | Rendimiento | 🟡 | sin test E2E de tiempo; medible vía `scans_log.duration_ms` |
| RNF-02 | Latencia de alerta < 24 h tras publicación del boletín | Rendimiento | ✅ | cooldown 24 h en `scripts/config.py::notify_cooldown_hours` |
| RNF-03 | Cobertura de datos: 100 % de entradas matcheables detectadas | Calidad | 🟡 | medible por test E2E con boletín real (RF-22) |
| RNF-04 | Tasa de falsos positivos < 5 % | Calidad | 🟡 | métrica automatizada en `api/routers/metrics.py` (veredictos Fase 4 + alerta); baseline real aún sin medición |
| RNF-05 | Tests pytest >= 180, Vitest >= 30 | Mantenibilidad | ✅ | 433 pytest + 45 Vitest (commit Fase 4 + Rama D) |
| RNF-06 | CI corre en cada push y PR, gate obligatorio para CD | Mantenibilidad | ✅ | `.github/workflows/ci.yml` con jobs `backend`, `dashboard`, `gate` |
| RNF-07 | CD hace smoke-test de la cara pública tras cada push a `main` | Mantenibilidad | ✅ | `.github/workflows/cd.yml` |
| RNF-08 | Pull deploy automático cada 5 min (systemd timer + Linger) | Disponibilidad | ✅ | `scripts/systemd/sapi-pull.timer` |
| RNF-09 | Logrotate diario con 7 copias para logs operativos | Mantenibilidad | ✅ | `/etc/logrotate.d/sapi-pull` |
| RNF-10 | JWT firmado con HS256, secret cargado de `.env` (no en repo) | Seguridad | ✅ | `scripts/auth.py::create_access_token` |
| RNF-11 | Hashing de contraseñas con bcrypt | Seguridad | ✅ | `scripts/auth.py::hash_password` |
| RNF-12 | Token Hermes validado por header `X-Hermes-Token` contra `SERVICE_TOKEN_HERMES` | Seguridad | ✅ | `api/deps.py::require_hermes`, `tests/test_orquestador.py` |
| RNF-13 | CORS configurable vía `API_CORS_ORIGINS` (CSV en `.env`) | Seguridad | ✅ | `api/main.py::CORSMiddleware`, `scripts/config.py::cors_origins_list` |
| RNF-14 | Bind del API a `127.0.0.1` por defecto; reverse proxy externo hace TLS | Seguridad | ✅ | `/etc/systemd/system/sapi-api.service` |
| RNF-15 | `.env`, `data/sapi.db*`, `data/uploads/*` en `.gitignore` | Seguridad | ✅ | `.gitignore` raíz |
| RNF-16 | Cap máximo de 100 entries por request a `/api/boletines/{id}/structured` | Seguridad | ✅ | `api/routers/structured.py::_MAX_ENTRIES_PER_REQUEST` |
| RNF-17 | Rate limiting en endpoints sensibles (login, upload) | Seguridad | ✅ | `api/middleware.py::RateLimitMiddleware`, `tests/test_rate_limit.py` |
| RNF-18 | HTTPS forzado en producción (Caddy externo) | Seguridad | ✅ | Caddy externo del proveedor |
| RNF-19 | Failover del pull deploy: si un build falla, el `dist/` viejo sigue activo | Disponibilidad | ✅ | `set -euo pipefail` en `pull_deploy.sh` aborta antes del restart |
| RNF-20 | Documentación operacional en `AGENTS.md` | Mantenibilidad | ✅ | `AGENTS.md` actualizado |
| RNF-21 | Specs formalizadas en `Specs/` (00-06) | Mantenibilidad | ✅ | esta carpeta |
| RNF-22 | Multi-tenant: aislamiento por `user_id` en `watchlist`, `portfolio`, `detections` | Seguridad | ✅ | `scripts/db.py`, `api/deps.py` |
| RNF-23 | Pydantic valida toda entrada/salida de la API | Seguridad | ✅ | `scripts/schemas.py`, FastAPI dependency injection |
| RNF-24 | `app.db` con FK activadas y `check_same_thread=False` | Robustez | ✅ | `scripts/db.py::connect()` |
| RNF-25 | Logs estructurados en `/var/log/sapi-pull.log` y journal de systemd | Observabilidad | ✅ | `scripts/pull_deploy.sh`, `scripts/systemd/sapi-pull.service` |
| RNF-26 | Métricas operacionales (processing time, error rate, queue depth) accesibles desde dashboard | Observabilidad | ✅ | `api/routers/metrics.py`, `dashboard/src/pages/Monitoring.tsx` |
| RNF-27 | Alertas automáticas cuando una métrica cae fuera de rango | Observabilidad | ✅ | `scripts/monitoring.py` + CLI `metrics-check` + campo `alerts` en `/api/admin/metrics` |

## Notas

- **RNF-04** (falsos positivos < 5 %) se mide con `false_positive_rate_pct`
  sobre los veredictos `discarded` acumulados por la cola de verificación
  Hermes (Fase 4). El < 5 % de objetivo exige acumular datos reales;
  hoy el umbral de alerta configurable parte de `FALSE_POSITIVE_THRESHOLD_PCT=20`.
- **RNF-17** (rate limiting) usa una ventana fija **en memoria** por
  worker: `login` (por IP, 60 s) y `upload` (por usuario/IP, 3600 s).
  Si la API se escala a varios workers, mover la contabilidad a Redis/DB.
- **RNF-26 / RNF-27** parametrizan los umbrales de alerta en `scripts/config.py`
  (en `.env.example`); el aviso sale por `SAPI_ALERT_EMAILS` vía
  `send_metric_alerts` (degradado a log sin SMTP configurado).