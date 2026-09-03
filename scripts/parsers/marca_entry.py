"""Parser multi-formato de entradas de marcas.

Expone ``MarcaEntryParser`` y ``MarcaEntry``. Aplica los patterns A, B y
C del paquete ``patterns/``. Cada pattern produce entradas con campos
homogéneos; el parser deduplica por ``expediente`` y opcionalmente
asigna ``page`` y ``estatus`` mediante callbacks del caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from scripts.parsers.patterns.pattern_a import extract as extract_a
from scripts.parsers.patterns.pattern_b import extract as extract_b
from scripts.parsers.patterns.pattern_c import extract as extract_c


@dataclass
class MarcaEntry:
    """Una entrada de marca parseada del boletín."""

    expediente: str
    marca: Optional[str] = None
    clase_niza: Optional[int] = None
    clase_especial: Optional[str] = None  # 'LC' para lemas comerciales
    titular: Optional[str] = None
    pais: Optional[str] = None
    fecha_inscripcion: Optional[str] = None  # ISO 8601 (YYYY-MM-DD)
    estatus: Optional[str] = None  # PUBLICADA, CONCEDIDA, NEGADA, ...
    page: Optional[int] = None
    excerpt: Optional[str] = None
    matcheable: bool = False
    es_figura: bool = False
    es_lema: bool = False
    productos_servicios: Optional[str] = None
    fuente_parsing: str = "pattern_a"


@dataclass
class ParseStats:
    total_inscripciones: int = 0
    entries_matcheables: int = 0
    entries_figura: int = 0
    entries_lema: int = 0
    entries_hermes_pending: int = 0
    pattern_a_count: int = 0
    pattern_b_count: int = 0
    pattern_c_count: int = 0


class MarcaEntryParser:
    """Parser multi-formato. Aplica patterns A → B → C en orden.

    Los patterns A y B extraen entradas matcheables (marca denominativa).
    Pattern C es un fallback para entradas con marca figurativa que
    quedan como ``matcheable=False`` para que Hermes visión las refine.

    Si ``page_lookup`` o ``section_lookup`` se proporcionan, el parser
    asigna ``page`` y ``estatus`` a cada entry automáticamente.
    """

    def __init__(
        self,
        page_lookup: Optional[callable] = None,
        section_lookup: Optional[callable] = None,
    ) -> None:
        """``page_lookup(text, position) -> int`` mapea una posición de
        carácter a número de página. Si es None, ``page`` queda None.

        ``section_lookup(text, position) -> str | None`` mapea una posición
        al estatus de la sección actual. Si es None, ``estatus`` queda None.
        """
        self._page_lookup = page_lookup
        self._section_lookup = section_lookup

    def parse(self, text: str) -> list[MarcaEntry]:
        """Devuelve la lista de entradas deduplicada por expediente."""
        entries = self._parse_raw(text)
        self._enrich(text, entries)
        return entries

    def parse_with_stats(self, text: str) -> tuple[list[MarcaEntry], ParseStats]:
        """Como ``parse`` pero también devuelve estadísticas."""
        entries = self._parse_raw(text)
        self._enrich(text, entries)
        stats = ParseStats(
            total_inscripciones=len(entries),
            entries_matcheables=sum(1 for e in entries if e.matcheable),
            entries_figura=sum(1 for e in entries if e.es_figura),
            entries_lema=sum(1 for e in entries if e.es_lema),
            entries_hermes_pending=sum(
                1 for e in entries if not e.matcheable
            ),
            pattern_a_count=sum(
                1 for e in entries if e.fuente_parsing == "pattern_a"
            ),
            pattern_b_count=sum(
                1 for e in entries if e.fuente_parsing == "pattern_b"
            ),
            pattern_c_count=sum(
                1 for e in entries if e.fuente_parsing == "pattern_c"
            ),
        )
        return entries, stats

    def _parse_raw(self, text: str) -> list[MarcaEntry]:
        seen: dict[str, MarcaEntry] = {}

        for raw in extract_a(text):
            entry = self._build_entry(raw, fuente="pattern_a")
            if entry.expediente and entry.expediente in seen:
                existing = seen[entry.expediente]
                if not existing.marca and entry.marca:
                    seen[entry.expediente] = entry
                continue
            if entry.expediente:
                seen[entry.expediente] = entry
            else:
                seen[f"__{id(entry)}"] = entry

        for raw in extract_b(text):
            entry = self._build_entry(raw, fuente="pattern_b")
            if entry.expediente and entry.expediente in seen:
                existing = seen[entry.expediente]
                if entry.marca and (
                    not existing.marca
                    or len(entry.marca) > len(existing.marca)
                ):
                    seen[entry.expediente] = entry
                continue
            if entry.expediente:
                seen[entry.expediente] = entry
            else:
                seen[f"__{id(entry)}"] = entry

        for raw in extract_c(text):
            entry = self._build_entry(raw, fuente="pattern_c")
            if entry.expediente and entry.expediente in seen:
                seen[entry.expediente].es_figura = True
                continue
            if entry.expediente:
                seen[entry.expediente] = entry
            else:
                seen[f"__{id(entry)}"] = entry

        return list(seen.values())

    def _enrich(self, text: str, entries: list[MarcaEntry]) -> None:
        """Asigna ``page`` y ``estatus`` a cada entry usando los lookups."""
        if not (self._page_lookup or self._section_lookup):
            return
        for entry in entries:
            if not entry.excerpt:
                continue
            idx = text.find(entry.excerpt[:80])
            if idx < 0:
                continue
            if self._page_lookup:
                entry.page = self._page_lookup(text, idx)
            if self._section_lookup:
                entry.estatus = self._section_lookup(text, idx)

    def _build_entry(self, raw: dict, fuente: str) -> MarcaEntry:
        marca = raw.get("marca")
        return MarcaEntry(
            expediente=raw.get("expediente") or "",
            marca=marca,
            clase_niza=raw.get("clase_niza"),
            clase_especial=raw.get("clase_especial"),
            titular=raw.get("titular"),
            pais=raw.get("pais"),
            fecha_inscripcion=raw.get("fecha_inscripcion"),
            matcheable=marca is not None,
            es_figura=raw.get("es_figura", False),
            es_lema=raw.get("clase_especial") == "LC",
            productos_servicios=raw.get("productos_servicios"),
            fuente_parsing=fuente,
            excerpt=raw.get("excerpt"),
        )


# ── API de compatibilidad para código que aún usa la firma antigua ──


def parse(text: str, page_lookup: Optional[callable] = None) -> list[MarcaEntry]:
    """Facade de compatibilidad. Equivalente a ``MarcaEntryParser(...).parse(text)``."""
    return MarcaEntryParser(page_lookup=page_lookup).parse(text)
