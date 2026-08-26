"""CRUD /api/users — solo admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import auth, db
from api.deps import get_db, require_admin
from api.routers._helpers import user_to_out
from scripts.schemas import UserCreateIn, UserOut

router = APIRouter()


@router.get("", response_model=list[UserOut])
async def list_users(
    _admin: db.UserRow = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    return [user_to_out(u) for u in db.users_list(conn)]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateIn,
    _admin: db.UserRow = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    if db.users_get_by_email(conn, body.email):
        raise HTTPException(status_code=409, detail="Email ya registrado")
    pwd_hash = auth.hash_password(body.password)
    uid = db.users_create(conn, body.email, pwd_hash, body.role)
    conn.commit()
    user = db.users_get(conn, uid)
    return user_to_out(user)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: int,
    _admin: db.UserRow = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    target = db.users_get(conn, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
    conn.commit()
