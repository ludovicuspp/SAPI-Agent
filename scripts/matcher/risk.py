"""Score de riesgo de una detección de marca.

Combina señales independientes del matcher en un valor 0..1 que
prioriza las detecciones:

- similitud de nombre,
- proximidad de clase Niza,
- solapamiento de productos/servicios (distingue),
- si el titular es conocido y distinto al nuestro (competidor real).

Devuelve ``float`` en [0, 1]. ``None`` se acepta solo en las señales
opcionales (``products_overlap``) y se trata como valor neutro.
"""


def risk_score(
    *,
    name_sim: float,
    class_proximity: float,
    products_overlap: bool | None,
    titular_known_conflict: bool = False,
) -> float:
    """Calcula el riesgo combinado de una detección.

    ``name_sim`` (0..1), ``class_proximity`` (0..1, ver
    ``matcher.nice_classes.proximity``), ``products_overlap``
    (True/False/None). ``titular_known_conflict`` aplica un bonus
    cuando sabemos que el titular es un tercero (competidor directo).
    """
    name_sim = max(0.0, min(1.0, name_sim))
    class_proximity = max(0.0, min(1.0, class_proximity))

    if products_overlap is None:
        overlap_factor = 0.5
    elif products_overlap:
        overlap_factor = 1.0
    else:
        overlap_factor = 0.0

    score = (
        0.5 * name_sim
        + 0.3 * class_proximity
        + 0.2 * overlap_factor
    )
    if titular_known_conflict:
        score = min(1.0, score * 1.1)
    return round(score, 3)