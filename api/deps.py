"""Dependencies inyectadas por FastAPI: conexión a DB, auth JWT, roles."""
from __future__ import annotations

import sqlite3
from typing import Iterator, Optional

from fastapi import Depends, Header, HTTPException, WebSocket

from scripts import db
from scripts.auth import InvalidTokenError, decode_token
from scripts.config import Settings, get_settings


def get_db() -> Iterator[sqlite3.Connection]:
    """Abre conexión SQLite por request y la cierra al final."""
    cfg = get_settings()
    conn = db.connect(cfg.sapi_db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    conn: sqlite3.Connection = Depends(get_db),
) -> db.UserRow:
    """Valida JWT del header Authorization: Bearer <token>."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.split(" ", 1)[1]
    cfg = get_settings()
    try:
        payload = decode_token(token, secret=cfg.jwt_secret)
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    user = db.users_get(conn, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def require_admin(
    user: db.UserRow = Depends(get_current_user),
) -> db.UserRow:
    """Solo permite pasar a admins."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol admin")
    return user


def get_ws_user(
    websocket: WebSocket, conn: sqlite3.Connection = Depends(get_db)
) -> Optional[db.UserRow]:
    """Valida el JWT de un WebSocket (query param `token`).

    Devuelve `None` si el token falta o es inválido; el endpoint WS decide
    cerrar (no aceptar) en ese caso.
    """
    token = websocket.query_params.get("token")
    if not token:
        return None
    cfg = get_settings()
    try:
        payload = decode_token(token, secret=cfg.jwt_secret)
    except InvalidTokenError:
        return None
    user = db.users_get(conn, int(payload["sub"]))
    if user is None:
        return None
    return user


def require_hermes(
    x_hermes_token: str = Header(None, alias="X-Hermes-Token"),
) -> None:
    """Valida service token de Hermes en headers."""
    cfg = get_settings()
    if not cfg.service_token_hermes:
        raise HTTPException(status_code=503, detail="Hermes service token no configurado")
    if not x_hermes_token or x_hermes_token != cfg.service_token_hermes:
        raise HTTPException(status_code=403, detail="Service token inválido")
