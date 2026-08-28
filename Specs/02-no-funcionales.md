# 02 — Requisitos no funcionales

Requisitos transversales de calidad, seguridad, rendimiento y
mantenibilidad. Mismo formato que `01-requisitos.md`.

| ID | Requisito | Categoría | Estado | Verificación |
|---|---|---|---|---|
| RNF-01 | Latencia de procesamiento del boletín < 15 min (objetivo de negocio) | Rendimiento | 🟡 | sin test E2E de tiempo; medible vía `scans_log.duration_ms` |
| RNF-02 | Latencia de alerta < 24 h tras publicación del boletín | Rendimiento | ✅ | cooldown 24 h en `scripts/config.py::notify_cooldown_hours` |
| RNF-03 | Cobertura de datos: 100 % de entradas matcheables detectadas | Calidad | 🟡 | medible por test E2E con boletín real (RF-22) |
| RNF-04 | Tasa de falsos positivos < 5 % | Calidad | ⬜ | sin métrica automatizada aún; Rama F+G |
| RNF-05 | Tests pytest >= 180, Vitest >= 30 | Mantenibilidad | ✅ | 186 pytest + 32 Vitest en commit `d175caf` |
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
| RNF-17 | Rate limiting en endpoints sensibles (login, upload) | Seguridad | ⬜ | no implementado; pendiente Rama D |
| RNF-18 | HTTPS forzado en producción (Caddy externo) | Seguridad | ✅ | Caddy externo del proveedor |
| RNF-19 | Failover del pull deploy: si un build falla, el `dist/` viejo sigue activo | Disponibilidad | ✅ | `set -euo pipefail` en `pull_deploy.sh` aborta antes del restart |
| RNF-20 | Documentación operacional en `AGENTS.md` | Mantenibilidad | ✅ | `AGENTS.md` actualizado |
| RNF-21 | Specs formalizadas en `Specs/` (00-06) | Mantenibilidad | ✅ | esta carpeta |
| RNF-22 | Multi-tenant: aislamiento por `user_id` en `watchlist`, `portfolio`, `detections` | Seguridad | ✅ | `scripts/db.py`, `api/deps.py` |
| RNF-23 | Pydantic valida toda entrada/salida de la API | Seguridad | ✅ | `scripts/schemas.py`, FastAPI dependency injection |
| RNF-24 | `app.db` con FK activadas y `check_same_thread=False` | Robustez | ✅ | `scripts/db.py::connect()` |
| RNF-25 | Logs estructurados en `/var/log/sapi-pull.log` y journal de systemd | Observabilidad | ✅ | `scripts/pull_deploy.sh`, `scripts/systemd/sapi-pull.service` |
| RNF-26 | Métricas operacionales (processing time, error rate, queue depth) accesibles desde dashboard | Observabilidad | ⬜ | Rama F del grill |
| RNF-27 | Alertas automáticas cuando una métrica cae fuera de rango | Observabilidad | ⬜ | Rama F del grill |

## Notas

- **RNF-04** (falsos positivos < 5 %) requiere un corpus etiquetado
  para medir. Hoy no hay baseline.
- **RNF-17** (rate limiting) se dejó para Rama D (seguridad), que
  decidimos diferir.
- **RNF-26 y RNF-27** son la base del módulo de monitoreo de Rama F.