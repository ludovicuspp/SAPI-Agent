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

EstatusLiteral = Literal[
    "PUBLICADA",
    "CONCEDIDA",
    "NEGADA",
    "DESISTIDA",
    "OPOSICION",
    "PRORROGADA",
    "CADUCA",
    "EN_TRAMITE",
    "PRIMERA_PUBLICACION",
    "SEGUNDA_PUBLICACION",
]


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

PORTFOLIO_ESTADOS = Literal[
    "Registrada", "Pendiente Resolución", "Desistida", "Abandonada", "Negada"
]
TIPOS_REGISTRO = Literal["Mixta", "Denominativa", "Grafica"]


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    expediente: Optional[str] = Field(default=None, max_length=100)
    class_nice: Optional[int] = Field(default=None, ge=1, le=45)
    notes: Optional[str] = None
    pais: str = "Venezuela"
    etiqueta: Optional[str] = None
    tipo_registro: Optional[TIPOS_REGISTRO] = None
    bufete: Optional[str] = Field(default=None, max_length=200)
    solicitud: Optional[str] = Field(default=None, max_length=80)
    fecha_solicitud: Optional[str] = Field(default=None, max_length=20)
    registro: Optional[str] = Field(default=None, max_length=80)
    fecha_registro: Optional[str] = Field(default=None, max_length=20)
    fecha_vencimiento: Optional[str] = Field(default=None, max_length=20)
    titular: Optional[str] = Field(default=None, max_length=300)
    tramitante: Optional[str] = Field(default=None, max_length=300)
    empresa_licenciada: Optional[str] = Field(default=None, max_length=300)
    productos_servicios: Optional[str] = None
    comentarios: Optional[str] = None
    status: Optional[PORTFOLIO_ESTADOS] = None


class PortfolioOut(BaseModel):
    id: int
    user_id: int
    name: str
    expediente: Optional[str]
    class_nice: Optional[int]
    status: Optional[str]
    last_checked_at: Optional[datetime]
    notes: Optional[str]
    pais: Optional[str]
    etiqueta: Optional[str]
    tipo_registro: Optional[str]
    bufete: Optional[str]
    solicitud: Optional[str]
    fecha_solicitud: Optional[str]
    registro: Optional[str]
    fecha_registro: Optional[str]
    fecha_vencimiento: Optional[str]
    titular: Optional[str]
    tramitante: Optional[str]
    empresa_licenciada: Optional[str]
    productos_servicios: Optional[str]
    comentarios: Optional[str]
    last_boletin_id: Optional[int]
    last_boletin_period: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class PortfolioHistoryOut(BaseModel):
    id: int
    portfolio_id: int
    user_id: int
    boletin_id: Optional[int]
    boletin_period: Optional[str]
    boletin_number: Optional[int]
    estado: Optional[str]
    snapshot: dict
    created_at: datetime


class PortfolioImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str] = []


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
    hermes_processed_at: Optional[datetime] = None
    uploaded_at: datetime
    processed_at: Optional[datetime]
    error: Optional[str]
    entries_matcheables: int = 0
    entries_hermes_pending: int = 0
    entries_figura: int = 0
    entries_lema: int = 0
    progress_step: Optional[str] = None
    progress_current_page: Optional[int] = None
    progress_total_pages: Optional[int] = None
    processing_batch: Optional[int] = None


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
    pais: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fuente_parsing: Optional[str] = None
    es_figura: bool = False
    es_lema: bool = False
    needs_hermes_reverify: bool = False


# ── /api/structured (Hermes → API) ────────────────────────────


class StructuredEntryIn(BaseModel):
    """Una entrada estructurada que Hermes entrega tras visión LLM."""

    expediente: str = Field(min_length=1, max_length=80)
    marca: str = Field(min_length=1, max_length=300)
    clase_niza: int = Field(ge=1, le=45)
    titular: str = Field(min_length=1, max_length=300)
    pais: Optional[str] = Field(default=None, max_length=100)
    estatus: EstatusLiteral
    pagina: Optional[int] = Field(default=None, ge=1)
    fuente: Source = "hermes_vision"
    confianza: Confidence = "medium"
    excerpt: Optional[str] = None
    fecha_inscripcion: Optional[str] = Field(default=None, max_length=20)

    @field_validator("estatus", mode="before")
    @classmethod
    def _normalize_estatus(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v


class StructuredBoletinIn(BaseModel):
    """Payload completo que Hermes envía a la API."""

    boletin_id: int
    entries: list[StructuredEntryIn] = Field(min_length=1)


# ── /api/summary ────────────────────────────────────────────────


class SummaryOut(BaseModel):
    watchlist_count: int
    portfolio_count: int
    boletines_count: int
    detections_count: int
    last_boletin_at: Optional[datetime]
    recent_detections: list[DetectionOut]
    recent_boletines: list[BoletinOut]


# ── /api/boletines/upload ───────────────────────────────────────


class UploadOut(BaseModel):
    boletin_id: int
    status: str


# ── /api/boletines/{id}/structured (response) ──────────────────


class StructuredOut(BaseModel):
    boletin_id: int
    status: str
    entries_added: int
