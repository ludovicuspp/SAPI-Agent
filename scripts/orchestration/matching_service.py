"""Servicio de matching reutilizable (watchlist + portfolio).

Centraliza dos operaciones que de otro modo viven duplicadas en el
pipeline de extracción y en el análisis retroactivo de marcas:

- ``match_watchlist_for_boletin``: compara las entradas de un boletín
  contra la watchlist del usuario (motor ``combined`` con regla G.1 de
  clase Niza) y persiste las detecciones ``match_kind='similar'``.
- ``analyze_boletines_for_user``: ante una marca recién cargada en
  watchlist/portafolio, re-lee los boletines ya extraídos del usuario
  (``extraction_json``) sin volver a extraer el PDF, re-ejecuta el
  matching y persiste las detecciones nuevas.

El análisis es idempotente: las detecciones ya existentes se saltan
(``INSERT OR IGNORE`` + guardas de coincidencia).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional

from scripts import db
from scripts.matcher import combined
from scripts.matcher.distinguish import products_intersect
from scripts.parsers.marca_entry import MarcaEntryParser
from scripts.orchestration.portfolio_sync import match_portfolio_by_identity


def match_watchlist_for_boletin(
    conn: sqlite3.Connection,
    user_id: int,
    boletin_id: int,
    matcheable_entries: Iterable[Any],
    thresholds: combined.Thresholds,
    *,
    source: str = "pdfplumber_text",
) -> int:
    """Matching de watchlist: nombre + clase Niza + distingue.

    Regla AND:

    - Nombre: similitud ≥ ``fuzzy_threshold`` (motor ``combined``: exact →
      fuzzy → phonetic).
    - Clase Niza: si watchlist y entry tienen clase definida y son
      distintas → no-match. Si alguna está ausente, se omite este
      filtro.
    - Distingue (productos/servicios): ambos textos pasan por
      ``products_intersect``. Si ``True`` → match. Si ``False`` →
      no-match. Si ``None`` (algún distingue ausente), fallback:
      match por nombre + clase sin exigir distingue.

    Persiste detecciones ``match_kind='similar'``. Idempotente por
    ``(boletin_id, user_id, expediente, watchlist_id)``.
    """
    entries = [e for e in matcheable_entries if e.marca]
    if not entries:
        return 0

    watch = db.watchlist_list_for_user(conn, user_id, only_active=True)
    if not watch:
        return 0

    watch_by_name = {w.name: w for w in watch}
    watch_names = list(watch_by_name.keys())
    candidate_names = [e.marca for e in entries]
    entries_by_name: dict[str, Any] = {}
    for e in entries:
        if e.marca and e.marca not in entries_by_name:
            entries_by_name[e.marca] = e

    # El motor ``combined`` aplica exact/fuzzy/phonetic, sin clases
    # (decidimos la regla de clase y distingue nosotros abajo).
    match_pairs = combined.find_matches(
        watch_names,
        candidate_names,
        thresholds,
    )

    created = 0
    for watch_name, candidate, mr in match_pairs:
        entry = entries_by_name.get(candidate)
        w = watch_by_name.get(watch_name)
        if not entry or not w:
            continue

        # Regla de clase Niza: si ambas están definidas y difieren → no.
        wc = w.class_nice
        ec = entry.clase_niza
        if wc is not None and ec is not None and wc != ec:
            continue

        # Regla de distingue (productos/servicios).
        overlap = products_intersect(
            getattr(w, "productos_servicios", None),
            getattr(entry, "productos_servicios", None),
        )
        # overlap ∈ {True, False, None}; False ⇒ no-match; True/None ⇒
        # continuar (None es fallback a match por nombre+clase).
        if overlap is False:
            continue

        if _watch_detection_exists(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            expediente=entry.expediente,
            watchlist_id=w.id,
        ):
            continue
        db.detections_add(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            watchlist_id=w.id,
            mark_name=candidate,
            similarity=mr.similarity,
            match_kind="similar",
            source=source,
            confidence=mr.confidence,
            matched_with=watch_name,
            expediente=entry.expediente,
            titular=entry.titular,
            class_nice=entry.clase_niza,
            page=entry.page,
            raw_excerpt=entry.excerpt,
            pais=entry.pais,
            fecha_inscripcion=entry.fecha_inscripcion,
            fuente_parsing=getattr(entry, "fuente_parsing", None) or (
                "hermes" if source != "pdfplumber_text" else "pdfplumber"
            ),
            es_figura=1 if entry.es_figura else 0,
            es_lema=1 if entry.es_lema else 0,
        )
        created += 1
    return created


def _watch_detection_exists(
    conn: sqlite3.Connection,
    *,
    boletin_id: int,
    user_id: int,
    expediente: Optional[str],
    watchlist_id: Optional[int],
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM detections"
        " WHERE boletin_id = ? AND user_id = ?"
        " AND expediente IS ? AND watchlist_id IS ? LIMIT 1",
        (boletin_id, user_id, expediente, watchlist_id),
    ).fetchone()
    return row is not None


def _entries_from_extraction_json(extraction_json: str) -> list[Any]:
    """Re-parsea las ``MarcaEntry`` de un boletín desde su extraction_json.

    No vuelve a extraer el PDF: las páginas de texto ya están persistidas
    y se reconstruye el texto junto a los índices página/sección que el
    parser usa para atribuir ``page``.
    """
    # Import diferido para evitar ciclo: processor -> matching_service.
    from scripts.orchestration.processor import (
        _build_parser_text,
        make_position_lookups,
    )

    data = json.loads(extraction_json)
    pages = data.get("pages", [])
    if not pages:
        return []
    parser_text = _build_parser_text(pages)
    page_lookup, section_lookup = make_position_lookups(parser_text)
    parser = MarcaEntryParser(
        page_lookup=page_lookup, section_lookup=section_lookup
    )
    entries, _stats = parser.parse_with_stats(parser_text)
    return entries


def analyze_boletines_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    run_watchlist: bool = True,
    run_portfolio: bool = True,
    source: str = "pdfplumber_text",
    thresholds: Optional[combined.Thresholds] = None,
) -> dict:
    """Re-analiza los boletines ya extraídos del usuario para una marca nueva.

    Corre el matching de watchlist y/o portafolio del usuario contra todos
    sus boletines con extracción persistida. Se usa al cargar una marca
    nueva en watchlist/portafolio, para (re)generar las detecciones que el
    procesamiento original no cubrió.

    Retorna ``{"boletines_analizados": int, "detecciones_creadas": int}``.
    """
    cfg_th = thresholds
    if cfg_th is None:
        from scripts.config import get_settings

        cfg = get_settings()
        cfg_th = combined.Thresholds.from_settings(
            cfg.match_threshold, cfg.fuzzy_threshold
        )

    boletines = db.boletines_list_extracted_for_user(conn, user_id)
    total_created = 0
    for boletin in boletines:
        if not boletin.extraction_json:
            continue
        try:
            entries = _entries_from_extraction_json(boletin.extraction_json)
        except (ValueError, KeyError, TypeError):
            continue
        matcheable = [e for e in entries if e.matcheable]
        created = 0
        if run_watchlist:
            created += match_watchlist_for_boletin(
                conn,
                user_id,
                boletin.id,
                matcheable,
                cfg_th,
                source=source,
            )
        if run_portfolio:
            created += match_portfolio_by_identity(
                conn,
                user_id,
                boletin.id,
                matcheable,
                source=source,
            )
        if created:
            conn.commit()
            total_created += created

    conn.commit()
    return {
        "boletines_analizados": len(boletines),
        "detecciones_creadas": total_created,
    }
