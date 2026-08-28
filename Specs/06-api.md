# 06 — API (v0)

**Versión:** v0 (sin prefijo `/api/v0/` aún; ver `RF-25`).
**Base URL producción:** `https://marcas.solutechve.net/api/`
**Base URL dev:** `http://localhost:8000/api/`
**OpenAPI:** `/docs` (Swagger UI), `/openapi.json`, `/redoc`

## Convenciones

- **Auth:** header `Authorization: Bearer <jwt>` salvo en `/auth/login`.
- **Hermes:** header `X-Hermes-Token: <SERVICE_TOKEN_HERMES>` en
  `/api/boletines/{id}/structured`.
- **Errores:** JSON `{ "detail": "<msg>" }` con códigos HTTP estándar.
- **Paginación:** los listados aceptan `?limit=N` (default 100).
- **Multi-tenant:** todo filtrado por `current_user.id` salvo rol admin.

## Endpoints

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/health` | no | Health check (`{"status":"ok"}`) |
| POST | `/api/auth/login` | no | Login; devuelve JWT (HS256, 8 h) |
| GET | `/api/users` | admin | Lista usuarios |
| POST | `/api/users` | admin | Crea usuario (`UserCreateIn`) |
| DELETE | `/api/users/{user_id}` | admin | Borra usuario |
| GET | `/api/watchlist` | sí | Lista watchlist del usuario actual |
| POST | `/api/watchlist` | sí | Añade entrada (`WatchlistIn`) |
| DELETE | `/api/watchlist/{watchlist_id}` | sí | Borra entrada |
| GET | `/api/portfolio` | sí | Lista portfolio del usuario actual |
| POST | `/api/portfolio` | sí | Añade entrada (`PortfolioIn`) |
| GET | `/api/boletines` | sí | Lista boletines del usuario |
| GET | `/api/boletines/{id}` | sí | Detalle de un boletín |
| POST | `/api/boletines/upload` | sí | Sube PDF (multipart, max 300 MB) → background task |
| WS | `/api/boletines/ws/{id}` | sí | WebSocket de progreso |
| POST | `/api/boletines/{id}/structured` | Hermes | Hermes postea entries (max 100, con `X-Hermes-Token`) |
| GET | `/api/detections` | sí | Lista detecciones (`?limit=200`) |
| GET | `/api/summary` | sí | Resumen agregado (counts + recientes) |

## Autenticación

```http
POST /api/auth/login
Content-Type: application/json

{ "email": "admin@solutechve.net", "password": "..." }
```

Respuesta:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 480
}
```

El cliente guarda `access_token` y lo envía en cada request:
```http
Authorization: Bearer eyJ...
```

Token expirado o inválido → **401**. Cliente limpia el token y
redirige a `/login` (lógica en `dashboard/src/lib/api.ts`).

## Subir un boletín

```http
POST /api/boletines/upload
Authorization: Bearer <jwt>
Content-Type: multipart/form-data

file: <pdf>                  # requerido, máx 300 MB
bulletin_number: 654         # opcional
period: "2026-02"            # opcional
```

Respuesta (202 Accepted):
```json
{ "boletin_id": 1, "status": "extracting" }
```

El procesamiento corre en background:
1. Crea fila en `boletines` (status='extracting').
2. `processor.process_pdf()` extrae + parsea + matchings + detections.
3. Emite eventos por WebSocket para progreso.

Si hay páginas con imágenes, `needs_hermes_review=1` y entra el flujo
de Hermes (ver `04-arquitectura.md`).

## WebSocket de progreso

```js
const ws = new WebSocket(`wss://.../api/boletines/ws/${boletin_id}`)
ws.onmessage = (e) => {
  const event = JSON.parse(e.data)
  // event.status: 'extracting' | 'extracted' | 'failed'
  // event.entries_parsed: number
}
```

## Hermes Vision / LLM

```http
POST /api/boletines/{boletin_id}/structured
X-Hermes-Token: <SERVICE_TOKEN_HERMES>
Content-Type: application/json

{
  "boletin_id": 1,
  "entries": [
    {
      "expediente": "2024-000001",
      "marca": "ACME TEST",
      "clase_niza": 25,
      "titular": "ACME HOLDINGS LLC",
      "pais": "VENEZUELA",
      "estatus": "PUBLICADA",
      "pagina": 1,
      "fuente": "hermes_vision",
      "confianza": "high",
      "excerpt": "Insc. 2024-000001 ...",
      "fecha_inscripcion": "2024-01-15"
    }
  ]
}
```

Validación:
- `estatus` debe estar en `EstatusLiteral` (10 valores SAPI).
- `fuente` ∈ {pdfplumber_text, hermes_llm, hermes_vision}.
- `confianza` ∈ {high, medium, low}.
- `clase_niza` ∈ 1-45 (rango Niza real).
- Máximo 100 entries por request (`_MAX_ENTRIES_PER_REQUEST`).

Respuesta (200):
```json
{ "boletin_id": 1, "status": "processed", "entries_added": 5 }
```

O `status: "already_processed"` si el boletín ya fue procesado.

Errores:
- **400** si `boletin_id` no coincide con la URL o excede 100 entries.
- **403** si `X-Hermes-Token` no coincide.
- **404** si el boletín no existe.
- **503** si `SERVICE_TOKEN_HERMES` no está configurado en `.env`.

## Resumen agregado (`/api/summary`)

```json
{
  "watchlist_count": 5,
  "portfolio_count": 12,
  "boletines_count": 3,
  "detections_count": 27,
  "last_boletin_at": "2026-08-27T19:00:00",
  "recent_detections": [...],   // últimos 10
  "recent_boletines": [...]     // últimos 5
}
```

## Modelos Pydantic (resumen)

| Modelo | Campos clave |
|---|---|
| `LoginIn` | email, password |
| `TokenOut` | access_token, token_type, expires_in |
| `UserCreateIn` | email, password (min 8), role |
| `WatchlistIn` | name (1-200), class_nice (1-45), notes |
| `PortfolioIn` | name, expediente (max 100), class_nice, notes |
| `BoletinOut` | id, filename, status, needs_hermes_review, ... |
| `DetectionOut` | boletin_id, mark_name, similarity, source, confidence, ... |
| `StructuredEntryIn` | expediente, marca, clase_niza, titular, estatus, ... |
| `StructuredBoletinIn` | boletin_id, entries (min 1, max 100) |
| `StructuredOut` | boletin_id, status, entries_added |
| `SummaryOut` | counts + recent_* |

Definiciones completas en `scripts/schemas.py`.

## Versionado (futuro)

`RF-25` plantea prefijo `/api/v0/` (sustituyendo `/api/`). Plan:

1. Crear alias `/api/v0/*` que apunta a los mismos handlers.
2. Mantener `/api/*` por compatibilidad durante 1 release.
3. Deprecar `/api/*` con warning en headers.
4. Eliminar `/api/*` en `v1`.

Sin breaking changes hoy; el switch es seguro.