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
| **`agent`** | CRUD de sus propios watchlists/portfolio/boletines, ver solo sus detecciones |

`Role = Literal["admin", "agent"]` en `scripts/schemas.py:17`.

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
- **CI/CD** con GitHub Actions (pull-based, no SSH directo).
- **186 tests** pytest + 32 Vitest, todos verdes.

Ver `README.md` y `AGENTS.md` para el detalle operacional.