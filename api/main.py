"""Punto de entrada de la API FastAPI."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    return _app


app = create_app()
