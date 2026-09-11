"""Política de candidatos a verificación Hermes (Fase 4).

Define qué detecciones entran automáticamente a la cola de verificación
LLM. La cola es asíncrona (pull-based): Hermes consulta ``GET
/api/detections/verify-queue`` y decide confirmar o descartar cada
candidato con un motivo. Hermes **no calcula similitud**: valida la
decisión binaria ya tomada por el matcher Python para reducir falsos
positivos (marcas cortas, confianza media/baja, familia de marca).
"""
from __future__ import annotations


def should_hermes_verify(
    *,
    source: str,
    match_kind: str,
    confidence: str,
    mark_name: str,
    is_family: bool = False,
) -> bool:
    """¿La detección entra a la cola de verificación Hermes?

    Reglas:
    - No: detecciones derivadas de Hermes (ya pasaron por visión LLM),
      ``own_status`` (caja propia del titular, no es falso positivo) ni
      ``titular`` (confianza siempre ``high``).
    - Sí: marca de 3 caracteres o menos, confianza ``medium``/``low``,
      o match por familia de marca.
    """
    if source != "pdfplumber_text":
        return False
    if match_kind not in ("conflict", "similar"):
        return False
    name = (mark_name or "").strip()
    if len(name) <= 3:
        return True
    if confidence in ("medium", "low"):
        return True
    if is_family:
        return True
    return False