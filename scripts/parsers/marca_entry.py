"""Heurística regex para extraer entradas de marcas del texto del boletín.

Este parser es deliberadamente conservador: prefiere ``None`` a alucinar.
Las páginas que no parsea van a ``needs_hermes_review=1`` para que
Hermes las procese en Fase 5 con visión multimodal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MarcaEntry:
    expediente: str
    marca: str
    clase_niza: int | None
    titular: str | None
    estatus: str | None
    page: int | None = None
    excerpt: str | None = None


_EXPEDIENTE_RE = re.compile(
    r"(?:Expediente|Solicitud|N[°ºo.]|Nro\.?)\s*[:.]?\s*"
    r"([A-Z]?-?\d{2,4}[-/]?\d{2,7})",
    re.IGNORECASE,
)

_CLASE_RE = re.compile(r"[Cc]lase[s]?\s*[:.]?\s*(\d{1,2})")

_TITULAR_RE = re.compile(
    r"(?:Titular|Solicitante)\s*[:.]\s+"
    r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\s,\.&'\-]{2,200}?)(?=\s{2,}|[;\n\r]|"
    r"Domicilio|Registro|Clase|Nacionalidad|Fecha)",
)

_MARCA_RE = re.compile(
    r"(?:Denominaci[óo]n|Marca|Signo)\s*[:.]\s+"
    r"([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9\s\-&'./]{1,150}?)(?=\s{2,}|[;\n\r]|"
    r"Clase|Titular|Solicitante|Expediente)",
)

_ESTATUS_RE = re.compile(
    r"(CONCEDIDA|NEGADA|OPOSICI[ÓO]N|DEVUELTA|PRIORIDAD|CADUCA|"
    r"DESISTIDA|PUBLICADA|PENDIENTE|REGISTRADA|EN\s+TR[ÁA]MITE)",
    re.IGNORECASE,
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip(" .,-")


def _split_into_blocks(text: str) -> list[tuple[int, str]]:
    """Divide el texto en bloques por separadores típicos de boletines.

    Cada bloque es ``(page_number, block_text)``. ``page_number`` se
    detecta por marcadores ``--- página N ---`` insertados por el
    processor al concatenar ``PageExtract.text``.
    """
    blocks: list[tuple[int, str]] = []
    current_page = 1
    current_lines: list[str] = []
    page_marker = re.compile(r"^---\s*p[áa]gina\s+(\d+)\s*---$", re.IGNORECASE)
    for line in text.splitlines():
        m = page_marker.match(line.strip())
        if m:
            if current_lines:
                blocks.append((current_page, "\n".join(current_lines)))
                current_lines = []
            current_page = int(m.group(1))
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append((current_page, "\n".join(current_lines)))
    return blocks


def parse(text: str) -> list[MarcaEntry]:
    """Devuelve entradas detectadas en el texto del boletín."""
    entries: list[MarcaEntry] = []

    for page_number, block in _split_into_blocks(text):
        exps = list(_EXPEDIENTE_RE.finditer(block))
        if not exps:
            continue

        for i, match in enumerate(exps):
            start = match.start()
            end = exps[i + 1].start() if i + 1 < len(exps) else len(block)
            snippet = block[start:end]

            clase_m = _CLASE_RE.search(snippet)
            titular_m = _TITULAR_RE.search(snippet)
            marca_m = _MARCA_RE.search(snippet)
            estatus_m = _ESTATUS_RE.search(snippet)

            marca = _clean(marca_m.group(1)) if marca_m else None
            if not marca:
                continue  # sin marca no es entrada útil

            try:
                clase_niza = int(clase_m.group(1)) if clase_m else None
                if clase_niza is not None and not (1 <= clase_niza <= 45):
                    clase_niza = None
            except ValueError:
                clase_niza = None

            entries.append(
                MarcaEntry(
                    expediente=_clean(match.group(1)) or "",
                    marca=marca,
                    clase_niza=clase_niza,
                    titular=_clean(titular_m.group(1)) if titular_m else None,
                    estatus=estatus_m.group(1).upper() if estatus_m else None,
                    page=page_number,
                    excerpt=snippet.strip()[:500],
                )
            )

    return entries
