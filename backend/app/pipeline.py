"""Orquestación de una consulta de punta a punta (single-turn, sin memoria).

    normalizar -> dedup -> clasificar (reglas + LLM) -> respuesta según categoría
                                                         ├─ faq_estatica  -> RAG
                                                         ├─ dato_dinamico -> mensaje fijo
                                                         ├─ otra_area     -> mensaje fijo
                                                         └─ con_humano    -> mensaje fijo + resumen (LLM)

El endpoint (`main.py`) solo orquesta: llama a `procesar_consulta` y persiste el
resultado. Toda la lógica de ramas vive acá.
"""

from __future__ import annotations

from typing import Callable, Optional

from .classifier import LLMClassifier, clasificar
from .config import (
    AMBIGUO,
    MENSAJE_CON_HUMANO,
    MENSAJE_DATO_DINAMICO,
    MENSAJE_OTRA_AREA,
    RESPUESTA_FAQ_PLACEHOLDER,
    Categoria,
)
from .normalization import RecentQueryCache, normalizar
from .rag import RespuestaRAG
from .schemas import ConsultaResponse

# faq_fn: recibe el texto normalizado y devuelve una RespuestaRAG.
FaqResponder = Callable[[str], RespuestaRAG]
# resumen_fn: recibe el texto normalizado y devuelve un resumen para el revisor.
ResumenFn = Callable[[str], str]


def procesar_consulta(
    texto: str,
    canal: str,
    *,
    cache: RecentQueryCache,
    llm_fn: Optional[LLMClassifier] = None,
    faq_fn: Optional[FaqResponder] = None,
    resumen_fn: Optional[ResumenFn] = None,
) -> ConsultaResponse:
    texto_norm = normalizar(texto)

    # ¿Casi-duplicado de una consulta reciente? -> respuesta cacheada, sin volver
    # a clasificar ni llamar al LLM/RAG.
    dup = cache.buscar_duplicado(texto_norm)
    if dup is not None and dup.payload is not None:
        cacheada = ConsultaResponse(**dup.payload)
        cacheada.es_duplicado = True
        return cacheada

    # Clasificar: reglas y, si es ambiguo, fallback al LLM.
    clf = clasificar(texto_norm, llm_fn=llm_fn)
    metodo, confianza, razon = clf.metodo, clf.confianza, clf.razon
    if clf.categoria == AMBIGUO:
        # Sin llm_fn (solo en desarrollo con SKIP_LLM): no hay certeza -> escalar.
        categoria: Categoria = Categoria.CON_HUMANO
        metodo, confianza = "sin_llm_fallback", 0.30
        razon = "reglas ambiguas y LLM deshabilitado"
    else:
        categoria = clf.categoria

    # Rama según categoría.
    resp = _responder(categoria, texto_norm, metodo, confianza, razon, faq_fn)

    # Para cualquier con_humano (regla directa, ambiguo, o derivación desde el
    # RAG): resumen breve para quien lo revise.
    if resp.categoria == Categoria.CON_HUMANO and resumen_fn is not None:
        resp.resumen = resumen_fn(texto_norm)

    # Guardar en el cache para deduplicar próximas consultas (con su resumen).
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
            # La clasificación (regla/llm) se mantiene; el RAG solo generó la
            # respuesta. Los rag_* aparecen únicamente cuando el RAG cambia la
            # categoría (derivación a con_humano).
            return ConsultaResponse(
                categoria=Categoria.FAQ_ESTATICA, respuesta=rag.respuesta, fuente=rag.fuente,
                confianza=rag.confianza, metodo_clasificacion=metodo, razon=razon,
            )
        # el RAG derivó a con_humano (baja confianza / sin fundamento)
        return ConsultaResponse(
            categoria=Categoria.CON_HUMANO, respuesta=MENSAJE_CON_HUMANO, fuente=None,
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

    # CON_HUMANO (por regla directa o fallback del LLM)
    return ConsultaResponse(
        categoria=Categoria.CON_HUMANO, respuesta=MENSAJE_CON_HUMANO, fuente=None,
        confianza=confianza, metodo_clasificacion=metodo, razon=razon,
    )
