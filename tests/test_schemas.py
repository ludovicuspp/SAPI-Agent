"""Tests de validación de esquemas Pydantic."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.schemas import (
    BoletinIn,
    PortfolioIn,
    StructuredBoletinIn,
    StructuredEntryIn,
    WatchlistIn,
)


class TestWatchlist:
    def test_valid(self):
        w = WatchlistIn(name="ACME", class_nice=25)
        assert w.name == "ACME"
        assert w.class_nice == 25

    def test_class_nice_bounds(self):
        with pytest.raises(ValidationError):
            WatchlistIn(name="X", class_nice=50)
        with pytest.raises(ValidationError):
            WatchlistIn(name="X", class_nice=0)

    def test_name_required(self):
        with pytest.raises(ValidationError):
            WatchlistIn(name="")


class TestPortfolio:
    def test_valid(self):
        p = PortfolioIn(name="MARCA", expediente="2026-1", class_nice=25)
        assert p.expediente == "2026-1"


class TestStructuredEntry:
    def test_valid(self):
        e = StructuredEntryIn(
            expediente="2026-1",
            marca="ACME",
            clase_niza=25,
            titular="ACME HOLDINGS",
            estatus="CONCEDIDA",
        )
        assert e.estatus == "CONCEDIDA"

    def test_estatus_uppercased(self):
        e = StructuredEntryIn(
            expediente="2026-1",
            marca="ACME",
            clase_niza=25,
            titular="X",
            estatus="concedida",
        )
        assert e.estatus == "CONCEDIDA"

    def test_clase_niza_bounds(self):
        with pytest.raises(ValidationError):
            StructuredEntryIn(
                expediente="x",
                marca="m",
                clase_niza=99,
                titular="t",
                estatus="X",
            )


class TestStructuredBoletin:
    def test_requires_entries(self):
        with pytest.raises(ValidationError):
            StructuredBoletinIn(boletin_id=1, entries=[])
