"""Esquemas Pydantic compartidos entre scripts/ y api/.

Validan entrada/salida de la API y los formatos que Hermes envía
en Fase 3 a ``/api/structured``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


MatchKind = Literal["similar", "own_status"]
Source = Literal["pdfplumber_text", "hermes_llm", "hermes_vision"]
Confidence = Literal["high", "medium", "low"]
Role = Literal["admin", "agent"]


# ── auth / users ───────────────────────────────────────────────


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role = "agent"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: Role
    active: bool
    created_at: datetime


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


# ── watchlist ──────────────────────────────────────────────────


class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    class_nice: Optional[int] = Field(default=None, ge=1, le=45)
    notes: Optional[str] = None


class WatchlistOut(BaseModel):
    id: int
    user_id: int
    name: str
    class_nice: Optional[int]
    notes: Optional[str]
    active: bool
    created_at: datetime


# ── portfolio ──────────────────────────────────────────────────


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    expediente: Optional[str] = Field(default=None, max_length=100)
    class_nice: Optional[int] = Field(default=None, ge=1, le=45)
    notes: Optional[str] = None


class PortfolioOut(BaseModel):
    id: int
    user_id: int
    name: str
    expediente: Optional[str]
    class_nice: Optional[int]
    status: Optional[str]
    last_checked_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime


# ── boletines ──────────────────────────────────────────────────


class BoletinIn(BaseModel):
    filename: str
    bulletin_number: Optional[int] = None
    period: Optional[str] = None


class BoletinOut(BaseModel):
    id: int
    uploaded_by: int
    filename: str
    file_path: str
    file_sha256: str
    bulletin_number: Optional[int]
    period: Optional[str]
    pages: Optional[int]
    status: str
    needs_hermes_review: bool
    uploaded_at: datetime
    processed_at: Optional[datetime]
    error: Optional[str]


# ── detections ─────────────────────────────────────────────────


class DetectionOut(BaseModel):
    id: int
    boletin_id: int
    user_id: int
    watchlist_id: Optional[int]
    portfolio_id: Optional[int]
    expediente: Optional[str]
    mark_name: str
    titular: Optional[str]
    class_nice: Optional[int]
    page: Optional[int]
    similarity: float
    match_kind: MatchKind
    source: Source
    confidence: Confidence
    raw_excerpt: Optional[str]
    detected_at: datetime
    notified_email: bool


# ── /api/structured (Hermes → API) ────────────────────────────


class StructuredEntryIn(BaseModel):
    """Una entrada estructurada que Hermes entrega tras visión LLM."""

    expediente: str = Field(min_length=1, max_length=80)
    marca: str = Field(min_length=1, max_length=300)
    clase_niza: int = Field(ge=1, le=45)
    titular: str = Field(min_length=1, max_length=300)
    pais: Optional[str] = Field(default=None, max_length=100)
    estatus: str = Field(min_length=1, max_length=80)
    pagina: Optional[int] = Field(default=None, ge=1)
    fuente: Source = "hermes_vision"
    confianza: Confidence = "medium"
    excerpt: Optional[str] = None

    @field_validator("estatus")
    @classmethod
    def _normalize_estatus(cls, v: str) -> str:
        return v.strip().upper()


class StructuredBoletinIn(BaseModel):
    """Payload completo que Hermes envía a la API."""

    boletin_id: int
    entries: list[StructuredEntryIn] = Field(min_length=1)
