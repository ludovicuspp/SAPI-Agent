# 00 — Overview

## Producto

**SAPI-Agent** es un sistema de monitoreo de marcas registradas en el
**SAPI Venezuela** (Servicio Autónomo de la Propiedad Intelectual).
Reduce el tiempo de procesamiento del Boletín de la Propiedad
Industrial de **días a menos de 15 minutos**, y avisa de posibles
conflictos en menos de 24 h tras la publicación.

## Objetivo de negocio

| KPI | Meta |
|---|---|
| Tiempo de procesamiento del boletín | < 15 min |
| Latencia de alerta tras publicación | < 24 h |
| Cobertura de datos extraídos | 100 % (cero omisiones) |
| Falsos positivos del matching | < 5 % (verificables vía Hermes Vision) |

## Alcance (qué sí)

- Ingesta de boletines en PDF subidos por usuarios del sistema.
- Extracción de texto (`pdfplumber` + fallback `pymupdf`).
- Estructuración por patrones A/B/C (`scripts/parsers/`).
- Revisión visual con **Hermes Vision** (LLM multimodal) para páginas
  con imágenes o texto de baja confianza.
- Matching **siempre en Python** (exacto + fuzzy + fonético).
- Notificaciones por **email** cuando hay coincidencias.
- Dashboard React multi-tenant con resumen, boletines, detecciones,
  watchlist, portfolio y admin de usuarios.

## Alcance (qué NO)

- **No** scrapeamos `sapi.gob.ve` (los boletines los suben usuarios).
- **No** automatizamos login a WEBPI (reCAPTCHA v3 — bloqueante).
- **No** enviamos notificaciones por canales distintos a email
  (sin SMS, sin push, sin Slack) — ver `01-requisitos.md` RF-06.
- **No** soportamos idiomas distintos al español.
- **No** ejecutamos cálculo de similitud en el LLM (solo en Python).

## Actores y roles

| Rol | Capacidades |
|---|---|
| **`admin`** | CRUD de usuarios, ver todos los datos, configurar watchlists/portfolio de cualquier agente |
| **`propietario`** | CRUD de sus watchlists/portfolio/boletines, ver solo sus detecciones |
| **`empresa`** | Igual que `propietario` (sujeto a las mismas reglas de aislamiento) |
| **`agent`** | Legado en BD; `role ∈ {admin, propietario, empresa}` desde Fase 3 |

`Role = Literal["admin", "propietario", "empresa"]` en
`scripts/schemas.py` (`agent` solo legacy en BD).

## Capas de la aplicación

```
Frontend (dashboard React + Vite + Tailwind)
        │  HTTPS
        ▼
Reverse proxy (Caddy externo del proveedor)
        │  proxy_pass
        ▼
API (FastAPI + uvicorn, gestionada por systemd)
        │
        ├─► scripts/  (extracción, parsers, matcher, db, CLI)
        ├─► data/     (SQLite + uploads; gitignored)
        └─► Hermes    (orquestador de revisión visual, fuera de proceso)
```

Detalle en `04-arquitectura.md`.

## Estado del proyecto

- **Fases 1-5** completas y desplegadas en producción
  (`https://marcas.solutechve.net`).
- **Endgame (Ramas A-H)**: RF-17/18/20/21/22/24/25/31 y
  RNF-04(medición)/17/26/27 implementados; queda RF-23 (SMTP real)
  pendiente de credenciales.
- **CI/CD** con GitHub Actions (pull-based, no SSH directo).
- **433 tests** pytest + 45 Vitest, todos verdes (CI: 4 skipped).

Pendientes reales: RF-23 (entregar email aviso de fallo de deploy
requiere `SMTP_USER`/`SMTP_PASSWORD` reales), baselines de RNF-01/03/04
(medición con boletines reales + veredictos Hermes acumulados).

Ver `README.md` y `AGENTS.md` para el detalle operacional.