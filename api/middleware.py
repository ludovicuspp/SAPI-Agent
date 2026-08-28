"""Middleware que añade alias /api/v0/ -> /api/.

Mapea cualquier ruta que comience con /api/v0/ a su equivalente en /api/.
Esto permite introducir la versión v0 de la API sin romper clientes
existentes (que siguen usando /api/) y a la vez sentar las bases para
versionado futuro (v1, v2, etc.).

El header de respuesta lleva ``X-API-Version: v0`` para que el cliente
pueda saber qué versión está usando.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ApiVersioningMiddleware(BaseHTTPMiddleware):
    """Añade alias /api/v0/* → /api/* y header ``X-API-Version``."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.scope.get("path", "")
        if path.startswith("/api/v0/"):
            new_path = "/api/" + path[len("/api/v0/"):]
            request.scope["path"] = new_path
        elif path == "/api/v0":
            request.scope["path"] = "/api"

        response = await call_next(request)
        response.headers["X-API-Version"] = "v0"
        return response