# SAPI-Agent

Agente para monitoreo de marcas registradas en SAPI Venezuela
(Servicio Autónomo de la Propiedad Intelectual).

## ¿Qué hace?

Reduce de días a menos de 15 minutos el procesamiento del Boletín de
la Propiedad Industrial de Venezuela. Convierte PDFs estáticos en
inteligencia de mercado: detecta solicitudes similares a tu cartera
vigilada y alerta posibles conflictos en menos de 24 h tras la
publicación.

Detalles en [`docs/objetivos.md`](docs/objetivos.md).

## Arquitectura

```
PDF subido por usuario
  ↓
[API] guarda PDF + crea boletin status='pending'
  ↓
[scripts/processor.py] extrae texto con pdfplumber → boletin.extraction_json
  ↓
[API] marca needs_hermes_review=1 si hay páginas con imágenes
  ↓
[Hermes] lee SQLite → para páginas con imágenes usa LLM multimodal
  ↓
[Hermes] POST /api/structured con JSON normalizado
  ↓
[API] valida (Pydantic), persiste, corre matcher (exacto+fuzzy+fonético),
      envía email si hay coincidencias, expone en dashboard
```

Más detalle en [`docs/arquitectura.md`](docs/arquitectura.md) y
[`docs/flujo-hermes.md`](docs/flujo-hermes.md) (escritos en Fase 6).

## Capas

| Capa | Carpeta | Stack | Fase |
|---|---|---|---|
| Procesamiento | `scripts/` | Python 3.14, pdfplumber, rapidfuzz, jellyfish | 2 |
| API | `api/` | FastAPI, SQLite | 3 |
| Dashboard | `dashboard/` | React + TypeScript + Vite | 4 |
| Orquestador | `hermes/` | Hermes Agent (CLI ya instalada) | 5 |

## Estructura

```
SAPI-Agent/
├── README.md
├── AGENTS.md
├── .env.example
├── requirements.txt
├── data/              # SQLite + uploads + logs (gitignored)
├── docs/              # objetivos, arquitectura, limitaciones
├── hermes/            # skill + crons + SOUL
├── scripts/           # (Fase 2)
├── api/               # (Fase 3)
├── dashboard/         # (Fase 4)
└── tests/             # (Fases 2-3)
```

## Quickstart (placeholder)

```bash
# Fase 1: cimientos (este commit)
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Los siguientes pasos (init-db, levantar API, dashboard) llegan con la
Fase 2 en adelante. Ver [`docs/quickstart.md`](docs/quickstart.md) cuando
exista (Fase 6).

## Limitaciones

- **WEBPI requiere login + reCAPTCHA v3**: no se automatiza. La
  consulta de estatus de expedientes propios se nutre de los boletines
  que los usuarios suben al sistema.
- **WEBPI horario**: 8:00 AM – 11:30 PM hora Venezuela.
- Los PDFs de los boletines los comparten los usuarios del sistema;
  no se scrapean de `sapi.gob.ve`.

Detalle en [`docs/limitaciones.md`](docs/limitaciones.md) (Fase 6).
