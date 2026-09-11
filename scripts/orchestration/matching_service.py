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
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from scripts import db
from scripts.matcher import combined
from scripts.matcher.distinguish import products_intersect
from scripts.matcher.exact import exact_score
from scripts.matcher.family import core_tokens, family_score
from scripts.matcher.fuzzy import fuzzy_score
from scripts.matcher.hermes_policy import should_hermes_verify
from scripts.matcher.nice_classes import proximity
from scripts.matcher.phonetic import phonetic_score
from scripts.matcher.risk import risk_score
from scripts.parsers.marca_entry import MarcaEntryParser
from scripts.orchestration.portfolio_sync import (
    match_portfolio_by_identity,
    match_portfolio_conflicts,
)
from scripts.lapsos import rebuild_alerts_for_boletin


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

    Dos tipos de watchlist (columna ``watchlist.kind``):

    - ``'marca'`` (default): regla AND nombre + clase Niza + distingue.
      Si ``match_family=1`` también se acepta contención de familia
      (``DRAGON`` ← ``DRAGON WINCH``). Sí ``entry.titular`` coincide con
      la marca vigilada no se filtra (una marca vigilada se detective
      aunque sea de su propio titular; la excepción es una watchlist con
      ``kind='titular'``, ver abajo).
    - ``'titular'``: vigila a un competidor. Compara ``entry.titular``
      contra ``watchlist.name`` (``TITULARES ESPAÑOLES`` no: compara el
      nombre de la persona/empresa). Detecta todo lo que registra ese
      titular.

    Persiste detecciones ``match_kind='similar'``. Idempotente por
    ``(boletin_id, user_id, expediente, watchlist_id)``.
    """
    entries = [e for e in matcheable_entries if e.marca]
    if not entries:
        return 0

    watch = db.watchlist_list_for_user(conn, user_id, only_active=True)
    if not watch:
        return 0

    created = 0
    for w in watch:
        if w.kind == "titular":
            created += _match_watchlist_titular(
                conn, user_id, w, entries, boletin_id, source
            )
        else:
            created += _match_watchlist_marca(
                conn, user_id, w, entries, boletin_id, source, thresholds
            )
    return created


def _match_watchlist_titular(
    conn: sqlite3.Connection,
    user_id: int,
    w: db.WatchlistRow,
    entries: list[Any],
    boletin_id: int,
    source: str,
) -> int:
    """Watchlist de competidor: detecta todo lo que registra un titular.

    Los titulares suelen traer fórmula legal truncada (``C.A.``, ``S.A.``,
    ``E.R.S.``) que el token_set_ratio ignora. Comparamos el contenido
    núcleo del titular con la marca vigilada.
    """
    created = 0
    for entry in entries:
        entry_marca = entry.marca
        entry_titular = entry.titular or ""
        if not entry_marca or not entry_titular:
            continue
        if not _titular_matches(w.name, entry_titular):
            continue
        if _watch_detection_exists(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            expediente=entry.expediente,
            watchlist_id=w.id,
        ):
            continue
        riesgo = risk_score(
            name_sim=1.0,
            class_proximity=proximity(w.class_nice, entry.clase_niza),
            products_overlap=products_intersect(
                getattr(w, "productos_servicios", None),
                getattr(entry, "productos_servicios", None),
            ),
            titular_known_conflict=True,
        )
        db.detections_add(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            watchlist_id=w.id,
            mark_name=entry_marca,
            similarity=1.0,
            match_kind="conflict",
            risk_score=riesgo,
            source=source,
            confidence="high",
            matched_with=f"titular:{w.name}",
            expediente=entry.expediente,
            titular=entry_titular,
            class_nice=entry.clase_niza,
            page=entry.page,
            raw_excerpt=entry.excerpt,
            pais=entry.pais,
            fecha_inscripcion=entry.fecha_inscripcion,
            disposicion=getattr(entry, "disposicion", None),
            tipo_disposicion=getattr(entry, "tipo_disposicion", None),
            fuente_parsing=getattr(entry, "fuente_parsing", None) or (
                "hermes" if source != "pdfplumber_text" else "pdfplumber"
            ),
            es_figura=1 if entry.es_figura else 0,
            es_lema=1 if entry.es_lema else 0,
            needs_hermes_reverify=1
            if should_hermes_verify(
                source=source,
                match_kind="conflict",
                confidence="high",
                mark_name=entry_marca,
            )
            else 0,
        )
        created += 1
    return created


@dataclass
class WatchMatch:
    """Resultado del matching de una watchlist de marca.

    ``name_sim``: similitud de nombre usada para la detección.
    ``is_family``: True si el match se alcanzó por contención de familia
    (la entry amplía la familia vigilada → posible conflicto).
    """

    name_sim: float
    is_family: bool


def watch_entry_matches(
    w: db.WatchlistRow,
    entry: Any,
    thresholds: combined.Thresholds,
) -> Optional[WatchMatch]:
    """Evalúa la regla de watchlist ``'marca'`` para una entrada.

    Devuelve ``None`` si no hay match; si lo hay, un ``WatchMatch`` con la
    similitud de nombre y si se alcanza por contención de familia
    (``is_family``). Aplica nombre + clase Niza (si ambas definidas) +
    distingue. La contención de familia opcional con ``w.match_family``
    permite cruzar clases distintas SOLO cuando el nombre de la entry
    contiene la familia vigilada (``DRAGON`` ← ``DRAGON WINCH``); para el
    resto de casos la regla AND de clase se mantiene.
    """
    if not entry.marca:
        return None
    wc = w.class_nice
    ec = entry.clase_niza
    class_differs = wc is not None and ec is not None and wc != ec

    e = exact_score(w.name, entry.marca)
    f = fuzzy_score(w.name, entry.marca)
    ph = phonetic_score(w.name, entry.marca)
    name_sim = max(e, f, 0.9 * ph)

    fam = family_score(w.name, entry.marca) if w.match_family else 0.0
    family_hit = fam >= 1.0 and name_sim >= 0.70
    if class_differs and not (w.match_family and family_hit):
        return None

    if name_sim >= thresholds.fuzzy:
        if fam >= 1.0:
            name_sim = max(name_sim, fam)
    elif family_hit:
        name_sim = fam
    else:
        return None

    if (
        products_intersect(
            getattr(w, "productos_servicios", None),
            getattr(entry, "productos_servicios", None),
        )
        is False
    ):
        return None
    is_family = w.match_family and fam >= 1.0 and (
        class_differs or name_sim < thresholds.fuzzy
    )
    return WatchMatch(name_sim=name_sim, is_family=is_family)


def watch_titular_matches(w: db.WatchlistRow, entry: Any) -> bool:
    """True si la watchlist ``'titular'`` detecta al titular de la entry."""
    return bool(entry.titular) and _titular_matches(w.name, entry.titular)


def _match_watchlist_marca(
    conn: sqlite3.Connection,
    user_id: int,
    w: db.WatchlistRow,
    entries: list[Any],
    boletin_id: int,
    source: str,
    thresholds: combined.Thresholds,
) -> int:
    """Watchlist de marca: nombre + clase Niza + distingue (+ familia)."""
    created = 0
    for entry in entries:
        res = watch_entry_matches(w, entry, thresholds)
        if res is None:
            continue
        name_sim = res.name_sim
        if _watch_detection_exists(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            expediente=entry.expediente,
            watchlist_id=w.id,
        ):
            continue
        # Familia de marca: la entrada amplía la familia vigilada (p. ej.
        # DRAGON WINCH para la watchlist DRAGON con match_family=1). Es un
        # posible conflicto con un tercero, no una variante del mismo nombre.
        is_family = res.is_family
        overlap = products_intersect(
            getattr(w, "productos_servicios", None),
            getattr(entry, "productos_servicios", None),
        )
        riesgo = risk_score(
            name_sim=name_sim,
            class_proximity=proximity(w.class_nice, entry.clase_niza),
            products_overlap=overlap,
            titular_known_conflict=False,
        )
        db.detections_add(
            conn,
            boletin_id=boletin_id,
            user_id=user_id,
            watchlist_id=w.id,
            mark_name=entry.marca,
            similarity=name_sim,
            match_kind="conflict" if is_family else "similar",
            risk_score=riesgo,
            source=source,
            confidence="high" if name_sim >= 0.95 else "medium",
            matched_with=w.name,
            expediente=entry.expediente,
            titular=entry.titular,
            class_nice=entry.clase_niza,
            page=entry.page,
            raw_excerpt=entry.excerpt,
            pais=entry.pais,
            fecha_inscripcion=entry.fecha_inscripcion,
            disposicion=getattr(entry, "disposicion", None),
            tipo_disposicion=getattr(entry, "tipo_disposicion", None),
            fuente_parsing=getattr(entry, "fuente_parsing", None) or (
                "hermes" if source != "pdfplumber_text" else "pdfplumber"
            ),
            es_figura=1 if entry.es_figura else 0,
            es_lema=1 if entry.es_lema else 0,
            needs_hermes_reverify=1
            if should_hermes_verify(
                source=source,
                match_kind="conflict" if is_family else "similar",
                confidence="high" if name_sim >= 0.95 else "medium",
                mark_name=entry.marca,
                is_family=is_family,
            )
            else 0,
        )
        created += 1
    return created


def _titular_matches(watch_name: str, titular: str) -> bool:
    """True si ``watch_name`` describe al titular (competidor detectado).

    Comparación de contenido núcleo (razones sociales y fórmulas legales
    se ignoran):
    - Coincidencia exacta del núcleo.
    - O contención: el watchlist (nombre del competidor) es un token
      completo del titular.
    """
    a = set(core_tokens(watch_name))
    b = set(core_tokens(titular))
    if not a or not b:
        return False
    if a.issubset(b) or b.issubset(a) or a & b:
        return True
    return False


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
    page_lookup, section_lookup, disposicion_lookup = make_position_lookups(
        parser_text
    )
    parser = MarcaEntryParser(
        page_lookup=page_lookup,
        section_lookup=section_lookup,
        disposicion_lookup=disposicion_lookup,
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
            created += match_portfolio_conflicts(
                conn,
                user_id,
                boletin.id,
                matcheable,
                source=source,
            )
        if created:
            conn.commit()
            total_created += created
        # Los lapsos legales derivan de las detecciones: se refrescan
        # siempre (idempotente) por si cambió el plazo configurado.
        rebuild_alerts_for_boletin(conn, boletin.id)

    conn.commit()
    return {
        "boletines_analizados": len(boletines),
        "detecciones_creadas": total_created,
    }
