"""Tests de autenticación (hash + JWT)."""
from __future__ import annotations

import time

import pytest

from scripts.auth import (
    InvalidTokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswords:
    def test_hash_and_verify(self):
        h = hash_password("MiClaveSegura123")
        assert verify_password("MiClaveSegura123", h)
        assert not verify_password("otra", h)

    def test_hash_is_unique_per_call(self):
        h1 = hash_password("x")
        h2 = hash_password("x")
        assert h1 != h2
        assert verify_password("x", h1)
        assert verify_password("x", h2)


class TestTokens:
    SECRET = "test-secret-32-chars-or-more-please"

    def test_roundtrip(self):
        token = create_access_token(
            42, "admin", secret=self.SECRET, expires_min=10
        )
        payload = decode_token(token, secret=self.SECRET)
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_invalid_secret_rejected(self):
        token = create_access_token(
            1, "agent", secret=self.SECRET, expires_min=10
        )
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret="otro-secreto")

    def test_expired_token_rejected(self):
        token = create_access_token(
            1, "agent", secret=self.SECRET, expires_min=0
        )
        time.sleep(1.1)  # aseguramos expiración
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret=self.SECRET)
