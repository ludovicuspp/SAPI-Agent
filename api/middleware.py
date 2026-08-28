"""Middleware que añade alias /api/v0/ -> /api/.

Mapea cualquier ruta que comience con /api/v0/ a su equivalente en /api/.
Esto permite introducir la versión v0 de la API sin romper clientes
existentes (que siguen usando /api/) y a la vez sentar las bases para
versionado futuro (v1, v2, etc.).

El header de respuesta lleva ``X-API-Version: v0`` para que el cliente
pueda saber qué versión está usando.

Implementación: ASGI middleware puro (no ``BaseHTTPMiddleware``), para
evitar incompatibilidades con ``request.scope`` mutation que se ven en
versiones recientes de Starlette con Python 3.12+.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ApiVersioningMiddleware:
    """Pure-ASGI middleware: /api/v0/* -> /api/* + header X-API-Version."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path.startswith("/api/v0/"):
            scope["path"] = "/api/" + path[len("/api/v0/"):]
        elif path == "/api/v0":
            scope["path"] = "/api"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Eliminar header previo si existe
                headers = [
                    (k, v) for k, v in headers
                    if k.lower() != b"x-api-version"
                ]
                headers.append((b"x-api-version", b"v0"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)