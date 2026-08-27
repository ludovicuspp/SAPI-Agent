"""Helper de arranque: añade rutas al ``sys.path`` para ejecutar como archivo.

Estos scripts se ejecutan como ``python hermes/skills/sapi-monitor/scripts/x.py``
(no como paquete, porque el directorio ``sapi-monitor`` lleva guion). Este
helper añade:

- la **raíz del repo** (para importar ``scripts.*``: db, extractores, matcher),
- el **directorio de scripts de la skill** (para importar módulos hermanos).

Es idempotente.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent  # .../hermes/skills/sapi-monitor/scripts


def _safe_add(path: Path) -> None:
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)


def repo_root() -> Path:
    """Raíz del repo: 4 niveles arriba de ``_bootstrap.py``."""
    return _HERE.parent.parent.parent.parent  # hermes/skills/sapi-monitor/scripts -> repo


def setup_paths() -> Path:
    """Añade raíz del repo y scripts de la skill a ``sys.path``.

    Devuelve la raíz del repo.
    """
    root = repo_root()
    _safe_add(root)
    _safe_add(_HERE)
    return root


def repo_db_path() -> Path:
    """Ruta por defecto a ``data/sapi.db``."""
    return repo_root() / "data" / "sapi.db"
