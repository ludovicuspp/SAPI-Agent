# Specs/ — Especificaciones del proyecto SAPI-Agent

Esta carpeta contiene las **especificaciones formales** del producto:
requisitos funcionales y no funcionales, restricciones, arquitectura,
modelo de datos y contrato de la API. Reflejan el **estado real**
del código (verificado contra `scripts/`, `api/`, `hermes/`).

## Idioma

- **Español** en todo el contenido (convención del repo).
- **Inglés** solo en identificadores de código, nombres de campos JSON,
  y nombres de variables de entorno (`VITE_API_BASE_URL`, `SMTP_HOST`).
- Anexos en inglés permitidos cuando la fuente externa está en inglés
  (ej. documentación de Pydantic, RFC de JWT).

## Estructura

| # | Archivo | Contenido |
|---|---|---|
| 00 | [`00-overview.md`](00-overview.md) | Visión general, alcance, actores y roles |
| 01 | [`01-requisitos.md`](01-requisitos.md) | Requisitos funcionales (RF-NN) con estado |
| 02 | [`02-no-funcionales.md`](02-no-funcionales.md) | Requisitos no funcionales (RNF-NN) con estado |
| 03 | [`03-restricciones.md`](03-restricciones.md) | Restricciones, supuestos y dependencias externas |
| 04 | [`04-arquitectura.md`](04-arquitectura.md) | Arquitectura de capas y flujo end-to-end |
| 05 | [`05-base-de-datos.md`](05-base-de-datos.md) | Esquema relacional (5 tablas) |
| 06 | [`06-api.md`](06-api.md) | Contrato REST + WebSocket (v0) |
| 07 | [`07-proxy.md`](07-proxy.md) | Snippets del reverse proxy (Caddy) para subir PDFs de 300 MB |

## Estado de implementación

Cada requisito en `01-requisitos.md` y `02-no-funcionales.md` lleva una
marca de estado en una columna dedicada:

| Marca | Significado |
|---|---|
| ✅ | Implementado y verificado por tests |
| 🟡 | Implementado parcialmente; falta cobertura o casos borde |
| ⬜ | Pendiente; no implementado |
| 🚫 | Descartado (con motivo en la nota) |

## Mantenimiento

- `Specs/` documenta el **contrato y estado deseado**.
- Cambios de esquema (`scripts/db.py`) ⇒ actualizar `05-base-de-datos.md`.
- Cambios de router (`api/routers/*.py`) ⇒ actualizar `06-api.md`.
- Cambios de CLI o comandos ⇒ actualizar `AGENTS.md` y `README.md`.
- Nuevos requisitos funcionales ⇒ añadir RF-NN en `01-requisitos.md`.

`Specs/` **no** es manual de usuario (eso va en `docs/`). Tampoco es
guía de trabajo para el agente IA (eso es `AGENTS.md`).

## Auditoría

Esta carpeta se generó a partir del estado real del repo a la fecha
del commit `d175caf`. Cualquier discrepancia con el código es un bug
de este documento (no del código).