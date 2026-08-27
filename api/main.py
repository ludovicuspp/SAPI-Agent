"""Punto de entrada de la API FastAPI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scripts.config import get_settings

from api.routers import (
    auth,
    boletines,
    detections,
    portfolio,
    structured,
    summary,
    uploads,
    users,
    watchlist,
)

# `dist/` del dashboard (build de producción con `npm run build`).
DASHBOARD_DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
_ASSETS_DIR = DASHBOARD_DIST / "assets"
_INDEX_FILE = DASHBOARD_DIST / "index.html"

# Rutas que SPA fallback nunca debe interceptar (pertenecen a la API/Swagger).
_NON_SPA_PREFIXES = ("api/", "docs", "openapi.json", "redoc")


def _mount_dashboard(app: FastAPI) -> None:
    """Sirve el build estático del dashboard y el fallback SPA.

    El orden importa: los routers de la API ya se registraron antes, así
    que el fallback solo actúa cuando no hubo match. Se monta `/assets`
    como estático con cache largo (Vite mete hash en los nombres) y se
    sirve `index.html` para el resto de rutas no-API.
    """
    if _ASSETS_DIR.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_ASSETS_DIR)),
            name="dashboard-assets",
        )

    favicon = DASHBOARD_DIST / "favicon.svg"
    if favicon.is_file():
        app.mount(
            "/favicon.svg",
            StaticFiles(directory=str(DASHBOARD_DIST), html=False),
            name="dashboard-favicon",
        )

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = "") -> FileResponse:
        if full_path and full_path.startswith(_NON_SPA_PREFIXES):
            raise HTTPException(status_code=404, detail="Ruta no encontrada")
        if not _INDEX_FILE.is_file():
            raise HTTPException(
                status_code=503,
                detail="Dashboard no compilado. Ejecuta `npm run build` en dashboard/",
            )
        return FileResponse(str(_INDEX_FILE))


def create_app() -> FastAPI:
    cfg = get_settings()
    _app = FastAPI(
        title="SAPI-Agent API",
        version="0.1.0",
        description="API para monitoreo de marcas SAPI Venezuela",
    )
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    _app.include_router(users.router, prefix="/api/users", tags=["users"])
    _app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"])
    _app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
    _app.include_router(boletines.router, prefix="/api/boletines", tags=["boletines"])
    _app.include_router(uploads.router, prefix="/api/boletines", tags=["uploads"])
    _app.include_router(detections.router, prefix="/api/detections", tags=["detections"])
    _app.include_router(structured.router, prefix="/api/boletines", tags=["structured"])
    _app.include_router(summary.router, prefix="/api/summary", tags=["summary"])

    @_app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    # El dashboard se monta al final para que no pise las rutas de la API.
    _mount_dashboard(_app)

    return _app


app = create_app()
