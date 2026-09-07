"""Clasificador de intención: reglas por keyword + fallback al LLM local.

`clasificar(texto, llm_fn=None)`:
  1. Aplica las reglas de `rules.py` sobre el texto normalizado sin acentos.
  2. Si alguna categoría destaca con suficiente margen -> se devuelve (metodo="regla").
  3. Si no -> AMBIGUO. Si se pasa `llm_fn`, se delega en el LLM
     (metodo="llm" o "llm_fallback_error"); si no, se devuelve AMBIGUO para que lo
     resuelva la capa superior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

from .config import AMBIGUO, PRIORIDAD_CATEGORIAS, Categoria
from .llm import LLMClasificacion
from .normalization import normalizar_match
from .rules import REGLAS

# Margen mínimo entre la 1ª y la 2ª categoría para fiarnos de las reglas.
# Si dos categorías puntúan casi igual, es ambiguo -> LLM.
_MARGEN_MINIMO = 1.0

# Tipo de retorno de la clasificación: una Categoria concreta o AMBIGUO.
Intencion = Union[Categoria, str]

# Firma del fallback: recibe el texto normalizado y devuelve una LLMClasificacion.
LLMClassifier = Callable[[str], LLMClasificacion]


@dataclass
class ResultadoClasificacion:
    categoria: Intencion
    metodo: str  # "regla" | "llm" | "llm_fallback_error" | "ambiguo"
    confianza: float
    razon: str = ""
    puntajes: dict[str, float] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)


def _puntuar_reglas(texto_match: str) -> tuple[dict[Categoria, float], dict[Categoria, list[str]]]:
    puntajes: dict[Categoria, float] = {c: 0.0 for c in REGLAS}
    matches: dict[Categoria, list[str]] = {c: [] for c in REGLAS}
    for categoria, reglas in REGLAS.items():
        for regla in reglas:
            m = regla.patron.search(texto_match)
            if m:
                puntajes[categoria] += regla.peso
                matches[categoria].append(m.group(0).strip())
    return puntajes, matches


def _confianza_desde_puntaje(top: float, segundo: float) -> float:
    """Heurística simple: cuanto más puntaje y más margen, más confianza."""
    if top <= 0:
        return 0.0
    margen = top - segundo
    # base por puntaje absoluto + bonus por margen, saturado en 0.95.
    score = 0.55 + 0.10 * min(top, 3.0) + 0.10 * min(margen, 2.0)
    return round(min(score, 0.95), 3)


def clasificar_por_reglas(texto_normalizado: str) -> ResultadoClasificacion:
    """Solo la parte de reglas. Devuelve AMBIGUO si no hay señal clara."""
    texto_match = normalizar_match(texto_normalizado)
    puntajes, matches = _puntuar_reglas(texto_match)

    ordenadas = sorted(
        puntajes.items(),
        key=lambda kv: (kv[1], -PRIORIDAD_CATEGORIAS.index(kv[0])),
        reverse=True,
    )
    (cat_top, punt_top), (_, punt_2) = ordenadas[0], ordenadas[1]

    puntajes_str = {c.value: round(p, 2) for c, p in puntajes.items() if p > 0}

    if punt_top <= 0 or (punt_top - punt_2) < _MARGEN_MINIMO:
        return ResultadoClasificacion(
            categoria=AMBIGUO,
            metodo="ambiguo",
            confianza=_confianza_desde_puntaje(punt_top, punt_2),
            puntajes=puntajes_str,
            keywords=matches.get(cat_top, []) if punt_top > 0 else [],
        )

    return ResultadoClasificacion(
        categoria=cat_top,
        metodo="regla",
        confianza=_confianza_desde_puntaje(punt_top, punt_2),
        razon="keywords: " + ", ".join(matches[cat_top]),
        puntajes=puntajes_str,
        keywords=matches[cat_top],
    )


def clasificar(
    texto_normalizado: str,
    llm_fn: Optional[LLMClassifier] = None,
) -> ResultadoClasificacion:
    """Clasificación completa: reglas y, si hace falta, fallback al LLM."""
    resultado = clasificar_por_reglas(texto_normalizado)
    if resultado.categoria != AMBIGUO:
        return resultado

    if llm_fn is None:
        return resultado  # queda AMBIGUO; lo resuelve la capa superior

    salida: LLMClasificacion = llm_fn(texto_normalizado)
    # metodo == "llm"           -> el LLM eligió una categoría válida
    # metodo == "llm_fallback_error" -> no se pudo parsear; salida.categoria = con_humano
    confianza = 0.60 if salida.metodo == "llm" else 0.30
    return ResultadoClasificacion(
        categoria=salida.categoria,
        metodo=salida.metodo,
        confianza=confianza,
        razon=salida.razon,
        puntajes=resultado.puntajes,
        keywords=resultado.keywords,
    )
