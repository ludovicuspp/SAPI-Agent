"""Middlewares ASGI puros: versión de API y rate limiting.

Implementados como ``ASGI`` puro (no ``BaseHTTPMiddleware``), para
evitar incompatibilidades con ``request.scope`` mutation en Starlette
reciente + Python 3.12+.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable

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


def _extract_user_id(scope: Scope) -> int | None:
    """Intenta extraer el user_id del token JWT (si está presente)."""
    try:
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                token = value.decode("utf-8").removeprefix("Bearer ").strip()
                if token:
                    from scripts.auth import decode_token
                    from scripts.config import get_settings
                    payload = decode_token(token, secret=get_settings().jwt_secret)
                    return int(payload["sub"])
        return None
    except Exception:
        return None


class RateLimitMiddleware:
    """Rate limiting ASGI puro: login por IP, upload por usuario.

    Ventana fija en memoria (sin persistencia entre restarts). Diseñado
    para un solo worker uvicorn (systemd unit). En caso de múltiples
    workers cada uno lleva su propia cuenta (estrictamente más laxo que
    el configurado, pero seguro).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        _windows: dict[tuple[str, str], tuple[float, int]] | None = None,
    ) -> None:
        self.app = app
        self._windows: dict[tuple[str, str], tuple[float, int]] = (
            _windows if _windows is not None else {}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        window_key: tuple[str, str] | None = None
        window_duration = 0.0
        limit = 0

        if method == "POST" and path == "/api/auth/login":
            from scripts.config import get_settings
            cfg = get_settings()
            client_ip = (scope.get("client") or ("0.0.0.0", 0))[0]
            window_key = ("login", client_ip)
            window_duration = 60.0
            limit = cfg.rate_limit_login_per_min

        elif method == "POST" and path == "/api/boletines/upload":
            from scripts.config import get_settings
            cfg = get_settings()
            user_id = _extract_user_id(scope)
            ident = str(user_id) if user_id else (scope.get("client") or ("0.0.0.0", 0))[0]
            window_key = ("upload", ident)
            window_duration = 3600.0
            limit = cfg.rate_limit_upload_per_hour

        if window_key is None:
            await self.app(scope, receive, send)
            return

        now = time.time()
        window = self._windows.get(window_key)
        if window is None or now - window[0] >= window_duration:
            self._windows[window_key] = (now, 1)
        else:
            start, count = window
            if count >= limit:
                remaining = int(window_duration - (now - start)) + 1
                body = {"detail": "Demasiadas peticiones. Intente más tarde."}
                payload = json.dumps(body).encode()
                await send({
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                        (b"retry-after", str(remaining).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": payload})
                return
            self._windows[window_key] = (start, count + 1)

        await self.app(scope, receive, send)