"""Clasificación de clases Niza como relación de conflicto.

Define grupos de clases relacionadas (según la clasificación de Niza)
para graduar la severidad de un posible conflicto de marca:

- ``same``: misma clase (conflicto directo).
- ``related``: clases del mismo bloque temático (conflicto probable).
- ``distant``: clases de bloques distintos pero con solapamiento
  temático reconocido (riesgo bajo, requiere nombres casi idénticos).
- ``unrelated``: sin relación.

Un conflicto fuerte (nombres muy parecidos) puede darse entre clases
``same``/``related``/``distant`` con umbrales de similitud crecientes.
"""

# Grupos de clases Niza relacionadas por bloque temático.
# El número de clase es entero (1..45). Los grupos no son disjuntos: una
# clase puede aparecer en varios bloques (p. ej. la 35 es de venta/servicios
# comerciales y complementa a casi todos los productos).
_GROUPS: list[set[int]] = [
    # Química / farmacia / cosmética / salud.
    {1, 3, 5, 10, 21},
    # Máquinas, herramientas, vehículos y sus partes.
    {7, 8, 12},
    # Productos metálicos / construcción / instalaciones.
    {6, 17, 19, 37},
    # Software / telecomunicaciones / servicios de telemática.
    {9, 38, 42},
    # Joyería / relojería / metal precioso.
    {14, 41},
    # Papel, cuero, textil, calzado, prendas.
    {16, 18, 24, 25},
    # Bebidas y alimentación.
    {29, 30, 31, 32, 33},
    # Juegos / deporte / entretenimiento.
    {28, 41, 43},
    # Hostelería / restauración / alojamiento.
    {43, 44},
    # Servicios comerciales / financieros / negocio.
    {35, 36},
    # Educación / ciencia / legal / diseño.
    {41, 42, 45},
]

# Clases de servicios comerciales (venta) que complementan a casi todos
# los productos. Considerar ``related`` con cualquier clase de producto.
_SERVICES_COMMERCIAL = {35}


def classes_related(a: int | None, b: int | None) -> str:
    """Clasifica la relación de conflicto entre dos clases Niza.

    Devuelve ``'same'``, ``'related'``, ``'distant'`` o ``'unrelated'``.
    ``None`` se trata como relación desconocida (``'distant'``: no hay
    evidencia en contra, se deja que el umbral de nombre lo decida).
    """
    if a is None or b is None:
        return "distant"
    a, b = int(a), int(b)
    if a == b:
        return "same"
    # La clase 35 (venta) complementa a cualquier clase de producto.
    if a in _SERVICES_COMMERCIAL or b in _SERVICES_COMMERCIAL:
        return "related"
    for group in _GROUPS:
        if a in group and b in group:
            return "related"
    return "unrelated"


def proximity(a: int | None, b: int | None) -> float:
    """Factor de proximidad de clase para el score de riesgo (0..1)."""
    rel = classes_related(a, b)
    return {"same": 1.0, "related": 0.6, "distant": 0.3, "unrelated": 0.0}[rel]
