"""POST /api/auth/login"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import auth, db
from scripts.config import get_settings
from scripts.schemas import LoginIn, TokenOut
from api.deps import get_db

router = APIRouter()


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_db)):
    user = db.users_get_by_email(conn, body.email)
    if user is None:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not user.active:
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    if not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    cfg = get_settings()
    token = auth.create_access_token(
        user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min,
    )
    return TokenOut(access_token=token, expires_in=cfg.jwt_expires_min)
