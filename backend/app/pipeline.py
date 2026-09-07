"""Orquestación de una consulta de punta a punta (single-turn, sin memoria).

    normalizar -> dedup -> clasificar (reglas + LLM) -> respuesta según categoría
                                                         └─ faq_estatica -> RAG

Paso 3: `faq_estatica` se responde con el RAG (`faq_fn`). El RAG puede además
deflectar a `con_humano` si el score es bajo (`rag_baja_confianza`) o si el LLM
no puede fundamentar la respuesta en el contexto (`rag_sin_fundamento`).
`con_humano` sigue siendo un placeholder hasta el Paso 4 (resumen + pendiente).
"""

from __future__ import annotations

from typing import Callable, Optional

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
from .rag import RespuestaRAG
from .schemas import ConsultaResponse

# Firma del responder RAG: recibe el texto normalizado y devuelve una RespuestaRAG.
FaqResponder = Callable[[str], RespuestaRAG]


def procesar_consulta(
    texto: str,
    canal: str,
    *,
    cache: RecentQueryCache,
    llm_fn: Optional[LLMClassifier] = None,
    faq_fn: Optional[FaqResponder] = None,
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

    resp = _responder(categoria, texto_norm, metodo, confianza, razon, faq_fn)

    # Registrar en el cache para deduplicar próximas consultas.
    # (El registro en SQLite se agrega en el Paso 4.)
    cache.registrar(texto_norm, payload=resp.model_dump())
    return resp


def _responder(
    categoria: Categoria,
    texto_norm: str,
    metodo: str,
    confianza: float,
    razon: str,
    faq_fn: Optional[FaqResponder],
) -> ConsultaResponse:
    if categoria == Categoria.FAQ_ESTATICA:
        if faq_fn is None:  # dev sin RAG
            return ConsultaResponse(
                categoria=categoria, respuesta=RESPUESTA_FAQ_PLACEHOLDER, fuente=None,
                confianza=confianza, metodo_clasificacion=metodo, razon=razon,
            )
        rag = faq_fn(texto_norm)
        if rag.categoria == Categoria.FAQ_ESTATICA:
            return ConsultaResponse(
                categoria=Categoria.FAQ_ESTATICA, respuesta=rag.respuesta, fuente=rag.fuente,
                confianza=rag.confianza, metodo_clasificacion=metodo, razon=razon,
            )
        # el RAG deflectó a con_humano (baja confianza / sin fundamento)
        return ConsultaResponse(
            categoria=Categoria.CON_HUMANO, respuesta=rag.respuesta, fuente=None,
            confianza=rag.confianza, metodo_clasificacion=rag.metodo,
            razon=f"RAG: {rag.metodo} (mejor score {rag.confianza})",
        )

    if categoria == Categoria.DATO_DINAMICO:
        return ConsultaResponse(
            categoria=categoria, respuesta=MENSAJE_DATO_DINAMICO, fuente=None,
            confianza=confianza, metodo_clasificacion=metodo, razon=razon,
        )

    if categoria == Categoria.OTRA_AREA:
        return ConsultaResponse(
            categoria=categoria, respuesta=MENSAJE_OTRA_AREA, fuente=None,
            confianza=confianza, metodo_clasificacion=metodo, razon=razon,
        )

    # CON_HUMANO
    return ConsultaResponse(
        categoria=Categoria.CON_HUMANO, respuesta=RESPUESTA_CON_HUMANO_PLACEHOLDER, fuente=None,
        confianza=confianza, metodo_clasificacion=metodo, razon=razon,
    )
