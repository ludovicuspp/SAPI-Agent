# SAPI-Agent Dashboard

SPA React para el monitoreo de marcas SAPI Venezuela.

## Setup

```bash
npm install
cp .env.example .env   # editar VITE_API_BASE_URL si es necesario
npm run dev            # http://localhost:5173
```

## Desarrollo

- `npm run dev` — desarrollo con hot reload
- `npm run build` — build de producción en `dist/`
- `npm run test` — ejecuta tests con Vitest

## Estructura

- `src/pages/` — Login, Summary, Boletines, Detections, Watchlist, Portfolio, Users
- `src/components/` — Layout, ProtectedRoute, AdminRoute, UploadZone
- `src/lib/` — api.ts (fetch wrapper), ws.ts (WebSocket), format.ts (utilidades)
- `src/store/` — Zustand (auth + uploads)
- `src/types/` — Tipos TypeScript espejo de Pydantic v2

## Autenticación

JWT en localStorage. El token se envía en `Authorization: Bearer` header.
Al recibir 401, se redirige a `/login`.
