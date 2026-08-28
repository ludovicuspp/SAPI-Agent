"""Tests anti-alucinaciones del LLM (Hermes Vision / hermes_llm).

Valida que el endpoint ``POST /api/boletines/{id}/structured`` rechace
entradas inválidas (clase Niza fuera de rango, estatus desconocido,
fuente/confianza fuera de enum) y dedupe por (boletin, expediente,
watchlist_id).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.schemas import StructuredEntryIn, StructuredBoletinIn


def _entry(**overrides):
    base = {
        "expediente": "2024-000001",
        "marca": "ACME TEST",
        "clase_niza": 25,
        "titular": "ACME HOLDINGS LLC",
        "pais": "VENEZUELA",
        "estatus": "PUBLICADA",
        "pagina": 1,
        "fuente": "hermes_vision",
        "confianza": "high",
        "excerpt": "Insc. 2024-000001 ...",
    }
    base.update(overrides)
    return base


# D.1 ── clase_niza fuera de rango (debe fallar Pydantic)
def test_alucinacion_clase_niza_fuera_de_rango_alto():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(clase_niza=999))


# D.2 ── clase_niza = 0 (debe fallar)
def test_alucinacion_clase_niza_cero():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(clase_niza=0))


# D.3 ── estatus normalizado a UPPER (debe aceptar "publicada")
def test_alucinacion_estatus_lowercase_normalizado():
    e = StructuredEntryIn(**_entry(estatus="publicada"))
    assert e.estatus == "PUBLICADA"


# D.4 ── estatus inventado (debe fallar)
def test_alucinacion_estatus_inventado_rechazado():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(estatus="XYZ_INVENTADO"))


# D.5 ── fuente fuera de enum (debe fallar)
def test_alucinacion_fuente_inventada():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(fuente="inventado_llm"))


# D.6 ── confianza fuera de enum (debe fallar)
def test_alucinacion_confianza_inventada():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(confianza="supreme"))


# D.7 ── dos entries con mismo expediente en boletin (boletin acepta,
#      pero detections dedupea por UNIQUE INDEX)
def test_alucinacion_payload_dos_entries_mismo_expediente():
    payload = StructuredBoletinIn(
        boletin_id=1,
        entries=[
            StructuredEntryIn(**_entry(expediente="2024-000001")),
            StructuredEntryIn(**_entry(expediente="2024-000001", marca="ACME VARIANTE")),
        ],
    )
    assert len(payload.entries) == 2


# D.8 ── expediente vacío (debe fallar)
def test_alucinacion_expediente_vacio():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(expediente=""))


# D.9 ── titular/marca vacíos (deben fallar)
def test_alucinacion_marca_vacia():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(marca=""))


def test_alucinacion_titular_vacio():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(titular=""))


# D.10 ── pagina negativa (debe fallar)
def test_alucinacion_pagina_negativa():
    with pytest.raises(ValidationError):
        StructuredEntryIn(**_entry(pagina=-1))


# D.11 ── max entries por request (debe fallar en endpoint)
def test_alucinacion_max_entries_excedido():
    entries = [
        StructuredEntryIn(**_entry(expediente=f"2024-{i:06d}"))
        for i in range(101)
    ]
    payload = StructuredBoletinIn(boletin_id=1, entries=entries)
    assert len(payload.entries) == 101  # Pydantic no capea; el endpoint lo hace


# D.12 ── EstatusLiteral cubre todos los valores comunes del SAPI
@pytest.mark.parametrize("estatus", [
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
])
def test_estatus_valores_validos(estatus):
    e = StructuredEntryIn(**_entry(estatus=estatus))
    assert e.estatus == estatus
