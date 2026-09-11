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


# ── Defaults derivados de la LPI/LOPA ───────────────────────────


class TestLapseDefaultsFromLpi:
    """Los defaults publicados en ``scripts/lapsos.py`` deben coincidir
    con los plazos de los artículos de la LPI/LOPA reimpresos por SAPI."""

    def test_pago_concesion_30_dias(self):
        d = [x for x in DEFAULT_LAPSOS if x["key"] == "pago_concesion"][0]
        assert d["dias_habiles"] == 30
        assert "art. 83" in d["label"]

    def test_subsanar_forma_30_dias(self):
        d = [x for x in DEFAULT_LAPSOS if x["key"] == "subsanar_forma"][0]
        assert d["dias_habiles"] == 30

    def test_recurso_negacion_15_dias_lopa(self):
        d = [x for x in DEFAULT_LAPSOS if x["key"] == "recurso_negacion"][0]
        assert d["dias_habiles"] == 15
        assert "LOPA" in d["label"]

    def test_recurso_inadmisible_15_dias(self):
        d = [x for x in DEFAULT_LAPSOS if x["key"] == "recurso_inadmisible"][0]
        assert d["dias_habiles"] == 15

    def test_recurso_caducidad_10_dias(self):
        d = [x for x in DEFAULT_LAPSOS if x["key"] == "recurso_caducidad"][0]
        assert d["dias_habiles"] == 10


# ── Parser de lapsos desde el boletín ───────────────────────────


class TestLapseParser:
    def test_treinta_dias_habiles_en_disposicion(self):
        from scripts.parsers.patterns.lapse import lapse_for_entry
        d, src = lapse_for_entry(
            "DEVUELTA DENTRO DE UN LAPSO DE TREINTA (30) DÍAS HÁBILES",
            None,
        )
        assert d == 30
        assert src == "regex_disposicion"

    def test_diez_dias_en_seccion(self):
        from scripts.parsers.patterns.lapse import lapse_for_entry
        d, src = lapse_for_entry(
            "comparecencia ante la Taquilla Integral dentro del lapso de diez (10) días",
            None,
        )
        assert d == 10
        assert src == "regex_disposicion"

    def test_sin_plazo_cae_a_fallback_lpi(self):
        from scripts.parsers.patterns.lapse import lapse_for_entry
        d, src = lapse_for_entry(
            "RESUELVE declarar SIN LUGAR el recurso interpuesto",
            None,
            fallback_lpi=15,
        )
        assert d == 15
        assert src == "fallback_lpi"

    def test_sin_plazo_ni_fallback_devuelve_none(self):
        from scripts.parsers.patterns.lapse import lapse_for_entry
        d, src = lapse_for_entry("texto sin plazo", None)
        assert d is None
        assert src == "none"

    def test_quince_dias_habiles_texto_lpi(self):
        from scripts.parsers.patterns.lapse import lapse_for_entry
        d, _ = lapse_for_entry(
            "dentro del plazo de quince (15) días hábiles a contar desde la publicación",
            None,
        )
        assert d == 15


# ── Override por entry leído del boletín ────────────────────────


class TestLapseOverride:
    def test_override_en_boletin_entry_prevalece_sobre_default(
        self, tmp_db, uid
    ):
        """Una entrada con ``lapse_dias_override`` explícito (leído del
        boletín) debe ganar sobre el default legal de ``lapse_config``."""
        from scripts.lapsos import lapse_dias_for_detection

        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "9" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01' WHERE id=?",
            (bid,),
        )
        did = _det(tmp_db, uid, bid, tipo="CONCESION")
        # Override del boletín: SAPI publica en este caso 45 días.
        tmp_db.execute(
            "INSERT INTO boletin_entries("
            " boletin_id, expediente, disposicion, lapse_dias_override,"
            " lapse_dias_source) VALUES (?,?,?,?,?)",
            (bid, "2026-001111",
             "PAGO DENTRO DE CUARENTA Y CINCO (45) DÍAS HÁBILES",
             45, "regex_disposicion"),
        )
        tmp_db.commit()
        det = tmp_db.execute(
            "SELECT * FROM detections WHERE id=?", (did,)
        ).fetchone()
        dias, src = lapse_dias_for_detection(tmp_db, det, default=30)
        assert dias == 45
        assert src == "regex_disposicion"

    def test_sin_override_cae_a_default(self, tmp_db, uid):
        from scripts.lapsos import lapse_dias_for_detection

        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "8" * 64
        )
        did = _det(tmp_db, uid, bid, tipo="CONCESION")
        tmp_db.commit()
        det = tmp_db.execute(
            "SELECT * FROM detections WHERE id=?", (did,)
        ).fetchone()
        dias, src = lapse_dias_for_detection(tmp_db, det, default=30)
        assert dias == 30
        assert src == "lapse_config"

    def test_rebuild_aplica_override(self, tmp_db, uid):
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "7" * 64
        )
        tmp_db.execute(
            "UPDATE boletines SET fecha_publicacion='2026-09-01' WHERE id=?",
            (bid,),
        )
        _det(tmp_db, uid, bid, tipo="CONCESION")
        tmp_db.execute(
            "INSERT INTO boletin_entries("
            " boletin_id, expediente, lapse_dias_override, lapse_dias_source)"
            " VALUES (?,?,?,?)",
            (bid, "2026-001111", 10, "regex_disposicion"),
        )
        tmp_db.commit()
        rebuild_alerts_for_boletin(tmp_db, bid)
        a = db.alerts_list_for_user(tmp_db, uid)[0]
        assert a.dias_habiles == 10


# ── Migración de defaults desde el placeholder 30 ──────────────


class TestMigrateLapseDefaults:
    def test_actualiza_defaults_viejos(self, tmp_db):
        """Una BD con los defaults placeholder (30) los cambia a los
        nuevos valores legales."""
        from scripts.db import _migrate_lapse_defaults
        tmp_db.execute("DELETE FROM lapse_config")
        tmp_db.executemany(
            "INSERT INTO lapse_config(key, label, dias_habiles,"
            " default_dias_habiles) VALUES (?,?,?,?)",
            [
                ("pago_concesion", "Pago (placeholder)", 30, 30),
                ("recurso_negacion", "Recurso (placeholder)", 30, 30),
                ("recurso_inadmisible", "Inadm (placeholder)", 30, 30),
                ("recurso_caducidad", "Caduc (placeholder)", 30, 30),
                ("subsanar_forma", "Subs forma (placeholder)", 30, 30),
                ("subsanar_fondo", "Subs fondo (placeholder)", 30, 30),
                ("oposicion", "Oposicion (placeholder)", 30, 30),
            ],
        )
        tmp_db.commit()
        _migrate_lapse_defaults(tmp_db)
        tmp_db.commit()
        cfg = {r["key"]: r["dias_habiles"] for r in tmp_db.execute(
            "SELECT key, dias_habiles FROM lapse_config"
        ).fetchall()}
        assert cfg["pago_concesion"] == 30  # sigue siendo 30
        assert cfg["recurso_negacion"] == 15  # actualizado
        assert cfg["recurso_inadmisible"] == 15
        assert cfg["recurso_caducidad"] == 10

    def test_no_pisa_edicion_manual(self, tmp_db):
        from scripts.db import _migrate_lapse_defaults
        tmp_db.execute("DELETE FROM lapse_config")
        # El admin bajó pago_concesion a 5 días.
        tmp_db.execute(
            "INSERT INTO lapse_config(key, label, dias_habiles,"
            " default_dias_habiles) VALUES (?,?,?,?)",
            ("pago_concesion", "Pago custom", 5, 30),
        )
        tmp_db.commit()
        _migrate_lapse_defaults(tmp_db)
        tmp_db.commit()
        cfg = tmp_db.execute(
            "SELECT dias_habiles FROM lapse_config WHERE key='pago_concesion'"
        ).fetchone()
        assert cfg["dias_habiles"] == 5  # NO se toca