"""Modelos Pydantic de entrada/salida del endpoint POST /consulta."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .config import Categoria


class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, description="Texto de la consulta del usuario.")
    canal: str = Field(..., description="Canal de origen: correo, chat, formulario, teléfono, ...")


class ConsultaResponse(BaseModel):
    categoria: Categoria
    respuesta: str
    fuente: Optional[str] = Field(
        None, description="Sección del documento citada (solo para faq_estatica)."
    )
    confianza: float = Field(
        ..., ge=0.0, le=1.0, description="Score de confianza de la clasificación/respuesta."
    )
    # Metadatos útiles para depurar / panel del frontend; no son parte del
    # contrato mínimo del enunciado.
    es_duplicado: bool = False
    metodo_clasificacion: str = Field(
        "regla",
        description="Cómo se clasificó: 'regla', 'llm', 'llm_fallback_error' o 'duplicado'.",
    )
    razon: str = Field("", description="Motivo de la clasificación (keywords o razón del LLM).")
