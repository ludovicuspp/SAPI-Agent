"""Hash de contraseñas (bcrypt) y tokens JWT.

Reusado por ``scripts/cli.py`` (Fase 2) y por la API (Fase 3).

Nota: usamos ``bcrypt`` directo en vez de ``passlib`` por la
incompatibilidad conocida entre ``passlib 1.7`` y ``bcrypt >= 4``
en Python 3.14. ``bcrypt`` directo es estable y suficiente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt


_BCRYPT_MAX_BYTES = 72


class InvalidTokenError(Exception):
    """Token JWT inválido o expirado."""


def _truncate(plain: str) -> bytes:
    """bcrypt sólo acepta hasta 72 bytes; truncamos explícitamente."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Devuelve el hash bcrypt de la contraseña en claro."""
    return bcrypt.hashpw(_truncate(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica la contraseña contra el hash."""
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: int,
    role: str,
    *,
    secret: str,
    expires_min: int,
) -> str:
    """Emite un JWT firmado con HS256.

    El payload incluye ``sub`` (id), ``role`` y ``exp``.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_min)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, *, secret: str) -> dict[str, Any]:
    """Decodifica y valida un JWT. Lanza ``InvalidTokenError`` si falla."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("Token expirado") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Token inválido: {e}") from e
