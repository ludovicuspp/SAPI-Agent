# Directorio `data/`

Volúmenes locales. **Nada de aquí se versiona** salvo los `.gitkeep`.

## Contenido

| Carpeta/archivo | Productor | Contenido |
|---|---|---|
| `sapi.db` | `scripts/cli.py init-db` (Fase 2) | Base de datos SQLite |
| `uploads/` | API (`POST /api/uploads`) | PDFs originales subidos por usuarios |
| `checkpoints/` | `processor.py` (extracción por lotes) | JSONL incremental de páginas extraídas (resume) |
| `hermes_runs/` | Hermes (Fase 5) | Logs de cada corrida |

## Limpieza

Para resetear todo:

```bash
rm -rf data/sapi.db* data/uploads/* data/checkpoints/* data/hermes_runs/*
python -m scripts.cli init-db   # recrea el esquema
```
