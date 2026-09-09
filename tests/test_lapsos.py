"""Tests del módulo de lapsos legales (Fase 2).

Cubre el cálculo de días hábiles, el mapa de disposición→lapso, la
reconstrucción de alertas por boletín y el estado derivado.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import db
from scripts.lapsos import (
    DEFAULT_LAPSOS,
    LAPSO_POR_ESTATUS,
    LAPSO_POR_TIPO,
    add_business_days,
    business_days_between,
    derivar_estado,
    dias_restantes,
    rebuild_alerts_for_boletin,
)
from scripts.schemas import DisposicionTipoLiteral


@pytest.fixture()
def uid(tmp_db: sqlite3.Connection) -> int:
    return db.users_create(tmp_db, "lapsos@x.y", "h")


def _det(
    tmp_db: sqlite3.Connection,
    uid: int,
    bid: int,
    *,
    expediente: str = "2026-001111",
    marca: str = "MARCA X",
    tipo: str | None = "CONCESION",
) -> int:
    return db.detections_add(
        tmp_db,
        boletin_id=bid,
        user_id=uid,
        mark_name=marca,
        similarity=1.0,
        match_kind="own_status",
        source="pdfplumber_text",
        confidence="high",
        expediente=expediente,
        tipo_disposicion=tipo,
    )


def _entry(expediente: str, estatus: str):
    return SimpleNamespace(
        expediente=expediente,
        marca="MARCA",
        clase_niza=None,
        clase_especial=None,
        titular="TITULAR",
        tramitante=None,
        disposicion=None,
        tipo_disposicion=None,
        pais=None,
        fecha_inscripcion=None,
        estatus=estatus,
        page=1,
        is_matcheable=True,
        is_figura=False,
        is_lema=False,
        productos_servicios=None,
        fuente_parsing="pattern_a",
        source=None,
        excerpt="x",
    )


# ── Cálculo de días hábiles ─────────────────────────────────────


class TestBusinessDays:
    def test_cero_dias_devuelve_mismo_dia(self):
        assert add_business_days(date(2026, 9, 9), 0) == date(2026, 9, 9)

    def test_cuenta_dias_hábiles(self):
        # miércoles 09/09/2026 + 2 → viernes 11/09/2026.
        assert add_business_days(date(2026, 9, 9), 2) == date(2026, 9, 11)

    def test_salta_fin_de_semana(self):
        # sábado 12/09 + 1 → lunes 14/09.
        assert add_business_days(date(2026, 9, 12), 1) == date(2026, 9, 14)

    def test_secuencia_larga(self):
        # viernes 28/08 + 5: 31/08 L, 01/09 M, 02/09 X, 03/09 J, 04/09 V.
        assert add_business_days(date(2026, 8, 28), 5) == date(2026, 9, 4)

    def test_between_incluye_extremo_b(self):
        # 09/09 mié → 16/09 mié: 5 días hábiles (10,11,14,15,16).
        assert business_days_between(date(2026, 9, 9), date(2026, 9, 16)) == 5


# ── Mapa disposición → lapso ────────────────────────────────────


class TestLapseMap:
    def test_cubre_todos_los_tipos_menos_revoca(self):
        """Todo tipo de disposición con efecto que abre lapso está mapeado.
        REVOCA no abre lapso (revocar no afecta el plazo de la marca)."""
        morado = set(DisposicionTipoLiteral.__args__)
        assert morado - {"REVOCA"} == set(LAPSO_POR_TIPO)
        assert "REVOCA" not in LAPSO_POR_TIPO

    def test_publicada_abre_oposicion(self):
        assert LAPSO_POR_ESTATUS == {"PUBLICADA": "oposicion"}

    def test_defaults_unicos_y_con_clave_valida(self):
        claves = [d["key"] for d in DEFAULT_LAPSOS]
        assert len(claves) == len(set(claves)) == 7
        for d in DEFAULT_LAPSOS:
            assert d["dias_habiles"] >= 1
            assert "label" in d and "key" in d


# ── Rebuild de alertas ──────────────────────────────────────────


class TestRebuildAlerts:
    def test_concesion_crea_alerta_de_pago(self, tmp_db, uid, monkeypatch):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "b" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01',"
            " status='extracted' WHERE id=?",
            (bid,),
        )
        did = _det(tmp_db, uid, bid, tipo="CONCESION")
        tmp_db.commit()

        n = rebuild_alerts_for_boletin(tmp_db, bid)
        assert n == 1
        rows = db.alerts_list_for_user(tmp_db, uid)
        assert len(rows) == 1
        a = rows[0]
        assert a.detection_id == did
        assert a.lapse_key == "pago_concesion"
        assert a.estado == "pendiente"
        assert a.dias_habiles == 30
        # 01/09/2026 mar + 30 hábiles ≈ 13/10/2026
        assert a.fecha_limite == "2026-10-13"
        assert a.fecha_publicacion == "2026-09-01"

    def test_publicada_abre_oposicion_desde_estatus(self, tmp_db, uid):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "c" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01',"
            " status='extracted' WHERE id=?",
            (bid,),
        )
        db.boletin_entry_upsert(tmp_db, bid, _entry("2026-009999", "PUBLICADA"))
        _det(tmp_db, uid, bid, tipo=None, expediente="2026-009999", marca="MARCA PUB")
        tmp_db.commit()

        n = rebuild_alerts_for_boletin(tmp_db, bid)
        assert n == 1
        a = db.alerts_list_for_user(tmp_db, uid)[0]
        assert a.lapse_key == "oposicion"

    def test_sin_fecha_publicacion_no_genera(self, tmp_db, uid):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "d" * 64
        )
        _det(tmp_db, uid, bid, tipo="NEGACION")
        tmp_db.commit()
        assert rebuild_alerts_for_boletin(tmp_db, bid) == 0
        assert db.alerts_list_for_user(tmp_db, uid) == []

    def test_resuelta_no_se_recalcula(self, tmp_db, uid):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "e" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01',"
            " status='extracted' WHERE id=?",
            (bid,),
        )
        _det(tmp_db, uid, bid, tipo="NEGACION")
        tmp_db.commit()
        rebuild_alerts_for_boletin(tmp_db, bid)
        alerta = db.alerts_list_for_user(tmp_db, uid)[0]
        db.alerts_resolve(tmp_db, alerta.id, user_id=uid, estado="cumplida")
        tmp_db.commit()

        # Reconstrue con el mismo plazo: la resuelta conserva su estado.
        rebuild_alerts_for_boletin(tmp_db, bid)
        a = db.alerts_list_for_user(tmp_db, uid)[0]
        assert a.estado == "cumplida"
        assert a.resolved_at is not None

    def test_cambio_de_plazo_refresca_pendiente(self, tmp_db, uid, monkeypatch):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "f" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01',"
            " status='extracted' WHERE id=?",
            (bid,),
        )
        _det(tmp_db, uid, bid, tipo="CONCESION")
        tmp_db.commit()
        rebuild_alerts_for_boletin(tmp_db, bid)
        assert db.alerts_list_for_user(tmp_db, uid)[0].fecha_limite == "2026-10-13"

        # El admin baja el plazo a 15 días hábiles.
        db.lapse_config_update(tmp_db, "pago_concesion", dias_habiles=15)
        tmp_db.commit()
        rebuild_alerts_for_boletin(tmp_db, bid)
        a = db.alerts_list_for_user(tmp_db, uid)[0]
        assert a.fecha_limite == "2026-09-22"
        assert a.dias_habiles == 15


# ── Estado derivado ─────────────────────────────────────────────


def test_derivar_estado_vencida_pasada_la_fecha():
    a = SimpleNamespace(estado="pendiente", fecha_limite="2020-01-01")
    assert derivar_estado(a, hoy=date(2026, 9, 9)) == "vencida"
    assert dias_restantes(a, hoy=date(2026, 9, 9)) < 0


def test_derivar_estado_pendiente_en_fecha():
    a = SimpleNamespace(estado="pendiente", fecha_limite="2026-09-15")
    assert derivar_estado(a, hoy=date(2026, 9, 9)) == "pendiente"
    assert dias_restantes(a, hoy=date(2026, 9, 9)) == 6