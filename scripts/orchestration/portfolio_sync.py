"""Matching de portfolio por identidad (#registro / #solicitud) + nombre.

Una marca del portafolio del usuario participa en el matching solo si
tiene ``#registro`` o ``#solicitud`` definido. La regla es:

1. Identidad: si ``portfolio.registro`` está definido, la entry debe
   tener ``entry.expediente`` igual (TRIM, mayúsculas). En su defecto,
   si ``portfolio.solicitud`` está definido, se compara contra
   ``entry.expediente``.
2. Nombre (filtro AND): ``portfolio.name`` y ``entry.marca`` deben tener
   similitud ≥ ``fuzzy_threshold`` (motor ``combined``).
3. Dedupe por familia: una marca con el mismo nombre que ya tiene una
   detección ``own_status`` en este boletín se omite (un mismo expediente
   no genera dos detecciones para la misma familia).

No hay regla temporal de actualización de estado: el matcher solo emite
detecciones y delega la gestión de estado del portafolio al flujo
manual (importación desde Excel / edición por el usuario).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from scripts import db
from scripts.matcher import combined
from scripts.matcher.distinguish import products_intersect
from scripts.matcher.exact import exact_score
from scripts.matcher.family import family_score
from scripts.matcher.fuzzy import fuzzy_score
from scripts.matcher.nice_classes import classes_related, proximity
from scripts.matcher.phonetic import phonetic_score
from scripts.matcher.risk import risk_score


def _identity_key(p: db.PortfolioRow) -> Optional[str]:
    """Clave de identidad priorizada: #REGISTRO → #SOLICITUD.

    Una marca sin ninguno de los dos no participa en el matching.
    """
    if p.registro and str(p.registro).strip():
        return str(p.registro).strip().upper()
    if p.solicitud and str(p.solicitud).strip():
        return str(p.solicitud).strip().upper()
    return None


def _detection_exists(
    conn: sqlite3.Connection,
    *,
    boletin_id: int,
    user_id: int,
    expediente: Optional[str],
    mark_name: Optional[str],
    portfolio_id: Optional[int] = None,
    watchlist_id: Optional[int] = None,
) -> bool:
    """Verifica si ya existe una detección idéntica para evitar duplicados."""
    query = (
        "SELECT 1 FROM detections WHERE boletin_id = ? AND user_id = ? "
        "AND expediente IS ? AND mark_name IS ? "
        "AND portfolio_id IS ? AND watchlist_id IS ? LIMIT 1"
    )
    row = conn.execute(query, (
        boletin_id, user_id,
        expediente, mark_name,
        portfolio_id, watchlist_id,
    )).fetchone()
    return row is not None


def match_portfolio_by_identity(
    conn: sqlite3.Connection,
    user_id: int,
    boletin_id: int,
    entries: Iterable[Any],
    *,
    source: str = "pdfplumber_text",
    thresholds: Optional[combined.Thresholds] = None,
) -> int:
    """Matching entre entradas del boletín y el portfolio por **identidad +
    nombre**.

    Una marca del portafolio solo participa si tiene ``#registro`` o
    ``#solicitud`` definido. La regla AND completa exige:

    - ``portfolio.registro == entry.expediente`` (si existe), o
      ``portfolio.solicitud == entry.expediente`` (en su defecto).
    - similitud de nombre ≥ ``fuzzy_threshold`` (``combined.score_pair``).
    - La entry no es un lema comercial (``clase_especial != 'LC'``).
    - Dedupe por familia: una marca con el mismo nombre que ya tiene
      una detección ``own_status`` en el boletín se omite.

    Retorna el número de detecciones nuevas.
    """
    portfolios = db.portfolio_list_for_user(conn, user_id)
    if not portfolios:
        return 0

    th = thresholds or combined.Thresholds(fuzzy=0.80)

    # Precomputar familias ya detectadas en este boletín (dedupe).
    existing_families: set[str] = set()
    rows = conn.execute(
        "SELECT DISTINCT p.name FROM detections d "
        "JOIN portfolio p ON p.id = d.portfolio_id "
        "WHERE d.boletin_id = ? AND d.user_id = ? "
        "AND d.match_kind = 'own_status' AND p.name IS NOT NULL",
        (boletin_id, user_id),
    )
    for r in rows:
        if r[0]:
            existing_families.add(r[0].upper())

    created = 0
    for entry in entries:
        entry_marca = getattr(entry, "marca", None)
        entry_exp = getattr(entry, "expediente", None)
        if not entry_marca or not entry_exp:
            continue
        if getattr(entry, "clase_especial", None) == "LC":
            continue
        entry_exp_key = str(entry_exp).strip().upper()

        # Agrupar portafolios por nombre (familia) y elegir el que
        # matchee por identidad con la entry. Si la familia ya está
        # detectada en este boletín, se omite.
        candidates_by_family: dict[str, list[db.PortfolioRow]] = {}
        for p in portfolios:
            ident = _identity_key(p)
            if ident is None or ident != entry_exp_key:
                continue
            candidates_by_family.setdefault(
                (p.name or "").upper(), []
            ).append(p)

        for family_name, family in candidates_by_family.items():
            if not family_name or family_name in existing_families:
                continue
            # Tomar el primer match de identidad de la familia y
            # verificar el nombre. No iteramos por clase Niza: la
            # identidad ya es única por (#registro o #solicitud).
            best = family[0]
            mr = combined.score_pair(best.name, entry_marca, th)
            if not mr.is_match:
                continue
            if _detection_exists(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                expediente=entry_exp,
                mark_name=entry_marca,
                portfolio_id=best.id,
            ):
                continue
            db.detections_add(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                portfolio_id=best.id,
                mark_name=entry_marca,
                similarity=mr.similarity,
                match_kind="own_status",
                source=source,
                confidence=mr.confidence,
                matched_with=best.name,
                expediente=entry_exp,
                titular=getattr(entry, "titular", None),
                class_nice=getattr(entry, "clase_niza", None),
                page=getattr(entry, "page", getattr(entry, "pagina", None)),
                raw_excerpt=getattr(entry, "excerpt", None),
                pais=getattr(entry, "pais", None),
                fecha_inscripcion=getattr(entry, "fecha_inscripcion", None),
                fuente_parsing="hermes" if source != "pdfplumber_text" else "pdfplumber",
                es_figura=1 if getattr(entry, "es_figura", False) else 0,
                es_lema=1 if getattr(entry, "es_lema", False) else 0,
            )
            existing_families.add(family_name)
            created += 1

    return created


# ── Conflicto de marcas (competidores) ─────────────────────────


def _name_similarity(a: str, b: str) -> float:
    """Similitud de nombre combinada (exact > fuzzy > phonetic)."""
    return max(
        exact_score(a, b),
        fuzzy_score(a, b),
        0.9 * phonetic_score(a, b),
    )


def _same_titular(
    entry_titular: Optional[str], portfolio_titular: Optional[str]
) -> bool:
    """True si ambos titulares están definidos y coinciden (variante propia).

    Si alguno está ausente no hay información → False (no bloquear).
    """
    if not entry_titular or not portfolio_titular:
        return False
    return fuzzy_score(entry_titular, portfolio_titular) >= 0.90


def _name_ok_by_class(
    rel: str, name_sim: float, fam: float
) -> bool:
    """Aplica el umbral de nombre según la cercanía de clase Niza.

    - ``same``: 0.80 (o contención de familia completa).
    - ``related``: 0.90 (o familia completa con similitud mínima).
    - ``distant``/``unrelated``: 0.95 (o familia completa con similitud
      mínima). Clases lejanas exigen nombre muy parecido para evitar
      falsos positivos.
    """
    if rel in ("same", "related"):
        base = 0.80 if rel == "same" else 0.90
        if name_sim >= base:
            return True
        return fam >= 1.0 and name_sim >= 0.70
    # distant / unrelated
    if name_sim >= 0.95:
        return True
    return fam >= 1.0 and name_sim >= 0.70


def match_portfolio_conflicts(
    conn: sqlite3.Connection,
    user_id: int,
    boletin_id: int,
    entries: Iterable[Any],
    *,
    source: str = "pdfplumber_text",
    thresholds: Optional[combined.Thresholds] = None,
) -> int:
    """Matching de conflicto/competencia: portfolio × entries por nombre +
    clase relacionada (excluyendo al propio titular).

    Regla de conflicto (``match_kind='conflict'``):

    - Nombre: ``_name_similarity`` ≥ umbral según ``classes_related``.
    - Clase: se permite ``same`` / ``related`` / ``distant``; la distancia
      solo sube el umbral de nombre.
    - Titular: si ``entry.titular`` y ``portfolio.titular`` coinciden
      (fuzzy ≥ 0.90), NO es conflicto (variante propia del titular).
    - Distingue: si ambos tienen productos y no hay intersección →
      no-match (refinamiento, no bloquea si falta en alguno).
    - Dedupe por familia: un nombre de portfolio que ya tiene una
      detección ``own_status``/``conflict`` para la misma entry se omite.

    Persiste ``risk_score`` (0..1) calculado con ``matcher.risk``.
    Retorna el número de detecciones nuevas.
    """
    portfolios = db.portfolio_list_for_user(conn, user_id)
    if not portfolios:
        return 0

    th = thresholds or combined.Thresholds(fuzzy=0.80)
    created = 0

    # Precomputar (por boletín) las familias ya detectadas para el usuario.
    existing_families: set[str] = set()
    rows = conn.execute(
        "SELECT DISTINCT p.name FROM detections d "
        "JOIN portfolio p ON p.id = d.portfolio_id "
        "WHERE d.boletin_id = ? AND d.user_id = ? "
        "AND p.name IS NOT NULL",
        (boletin_id, user_id),
    )
    for r in rows:
        if r[0]:
            existing_families.add(r[0].upper())

    for entry in entries:
        entry_marca = getattr(entry, "marca", None)
        if not entry_marca:
            continue
        if getattr(entry, "clase_especial", None) == "LC":
            continue

        entry_titular = getattr(entry, "titular", None)
        entry_clase = getattr(entry, "clase_niza", None)
        entry_prods = getattr(entry, "productos_servicios", None)

        for p in portfolios:
            pname = (p.name or "").upper()
            if not pname or pname in existing_families:
                continue
            if not p.name or not entry_marca:
                continue

            rel = classes_related(p.class_nice, entry_clase)
            if rel == "unrelated":
                continue

            name_sim = _name_similarity(p.name, entry_marca)
            fam = family_score(p.name, entry_marca)
            if not _name_ok_by_class(rel, name_sim, fam):
                continue

            # Excluir variantes del propio titular (misma persona registrando).
            if _same_titular(entry_titular, p.titular):
                continue

            overlap = products_intersect(p.productos_servicios, entry_prods)
            if overlap is False:
                continue

            if _detection_exists(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                expediente=entry.expediente,
                mark_name=entry_marca,
                portfolio_id=p.id,
            ):
                continue

            riesgo = risk_score(
                name_sim=name_sim,
                class_proximity=proximity(p.class_nice, entry_clase),
                products_overlap=overlap,
                titular_known_conflict=bool(p.titular and entry_titular),
            )
            confidence = "high" if name_sim >= 0.95 else "medium"
            db.detections_add(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                portfolio_id=p.id,
                mark_name=entry_marca,
                similarity=name_sim,
                match_kind="conflict",
                risk_score=riesgo,
                source=source,
                confidence=confidence,
                matched_with=p.name,
                expediente=entry.expediente,
                titular=entry_titular,
                class_nice=entry_clase,
                page=getattr(entry, "page", getattr(entry, "pagina", None)),
                raw_excerpt=getattr(entry, "excerpt", None),
                pais=getattr(entry, "pais", None),
                fecha_inscripcion=getattr(entry, "fecha_inscripcion", None),
                fuente_parsing="hermes" if source != "pdfplumber_text" else "pdfplumber",
                es_figura=1 if getattr(entry, "es_figura", False) else 0,
                es_lema=1 if getattr(entry, "es_lema", False) else 0,
            )
            existing_families.add(pname)
            created += 1

    return created
