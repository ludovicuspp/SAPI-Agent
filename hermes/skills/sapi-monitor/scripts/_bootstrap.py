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


_HERMES_ENV_LOADED = False


def load_repo_env(root: Path | None = None) -> None:
    """Carga selectivamente ``<repo>/.env`` para las variables del agente
    cuando no están ya en el entorno.

    El agente Hermes corre en el ``--workdir`` del repo pero sin el env
    exportado; los scripts de la skill (``progress.py``, ``submit.py``)
    necesitan ``HERMES_API_URL`` y ``SERVICE_TOKEN_HERMES`` para hablar con
    la API. Esto no reemplaza valores ya presentes en ``os.environ``.
    """
    global _HERMES_ENV_LOADED
    if _HERMES_ENV_LOADED:
        return
    import os

    root = root or repo_root()
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"").rstrip()
            if key in {"HERMES_API_URL", "SERVICE_TOKEN_HERMES"} and not os.environ.get(key):
                os.environ[key] = value
    _HERMES_ENV_LOADED = True
