"""Orquestación de una consulta de punta a punta (single-turn, sin memoria).

    normalizar -> dedup -> clasificar (reglas + LLM) -> respuesta según categoría

Paso 2: la respuesta de `faq_estatica` y `con_humano` son placeholders; el RAG
(Paso 3) y el resumen/pendiente (Paso 4) se enganchan después.
"""

from __future__ import annotations

from typing import Optional

from .classifier import LLMClassifier, clasificar
from .config import (
    AMBIGUO,
    MENSAJE_DATO_DINAMICO,
    MENSAJE_OTRA_AREA,
    RESPUESTA_CON_HUMANO_PLACEHOLDER,
    RESPUESTA_FAQ_PLACEHOLDER,
    Categoria,
)
from .normalization import RecentQueryCache, normalizar
from .schemas import ConsultaResponse


def procesar_consulta(
    texto: str,
    canal: str,
    *,
    cache: RecentQueryCache,
    llm_fn: Optional[LLMClassifier] = None,
) -> ConsultaResponse:
    texto_norm = normalizar(texto)

    # 1. ¿Casi-duplicado de una consulta reciente? -> devolver respuesta cacheada.
    dup = cache.buscar_duplicado(texto_norm)
    if dup is not None and dup.payload is not None:
        cacheada = ConsultaResponse(**dup.payload)
        cacheada.es_duplicado = True
        return cacheada

    # 2. Clasificar: reglas y, si es ambiguo, fallback al LLM.
    clf = clasificar(texto_norm, llm_fn=llm_fn)
    metodo = clf.metodo
    confianza = clf.confianza
    razon = clf.razon
    if clf.categoria == AMBIGUO:
        # Sin llm_fn (solo en desarrollo con SKIP_LLM): no hay certeza -> escalar.
        categoria: Categoria = Categoria.CON_HUMANO
        metodo = "sin_llm_fallback"
        confianza = 0.30
        razon = "reglas ambiguas y LLM deshabilitado"
    else:
        categoria = clf.categoria

    # 3. Respuesta según categoría.
    fuente: Optional[str] = None
    if categoria == Categoria.FAQ_ESTATICA:
        respuesta = RESPUESTA_FAQ_PLACEHOLDER
    elif categoria == Categoria.DATO_DINAMICO:
        respuesta = MENSAJE_DATO_DINAMICO
    elif categoria == Categoria.OTRA_AREA:
        respuesta = MENSAJE_OTRA_AREA
    else:  # CON_HUMANO
        respuesta = RESPUESTA_CON_HUMANO_PLACEHOLDER

    resp = ConsultaResponse(
        categoria=categoria,
        respuesta=respuesta,
        fuente=fuente,
        confianza=confianza,
        es_duplicado=False,
        metodo_clasificacion=metodo,
        razon=razon,
    )

    # 4. Registrar en el cache para la deduplicación de próximas consultas.
    #    (El registro en SQLite se agrega en el Paso 4.)
    cache.registrar(texto_norm, payload=resp.model_dump())
    return resp
