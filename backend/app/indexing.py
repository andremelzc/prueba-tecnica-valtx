"""Lectura y chunking de `documentos_referencia.docx` (sin dependencias de ML).

El contenido real está repartido entre:
  - `doc.paragraphs`  -> prosa de las 5 secciones
  - `doc.tables`      -> catálogo de productos (COD-ALF/BET/GAM) y tabla de
                         descuentos por volumen

Hay que recorrer el cuerpo EN ORDEN para saber a qué sección pertenece cada
tabla. Cada sección de prosa es un chunk; cada fila de tabla es un chunk aparte,
convertida a texto legible antes de generar el embedding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import docx
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

# Títulos reales del .docx (ya sin el prefijo "1.", "2.", ... que se perdió al
# transcribir a Word) -> nombre canónico de la fuente que se cita al usuario.
SECCIONES: dict[str, str] = {
    "catálogo de productos": "Catálogo de productos",
    "cómo solicitar un producto o servicio": "Cómo solicitar un producto o servicio",
    "política de devoluciones y garantías": "Política de devoluciones y garantías",
    "política de descuentos": "Política de descuentos",
    "preguntas frecuentes": "Preguntas frecuentes",
}


@dataclass
class Chunk:
    seccion: str          # fuente canónica que se cita
    texto: str            # lo que se indexa / se le pasa al LLM
    tipo: str             # "prosa" | "tabla"


def _match_seccion(texto: str) -> str | None:
    """Devuelve la fuente canónica si `texto` es uno de los títulos de sección."""
    base = texto.strip().lower()
    base = re.sub(r"\s*\((extracto|parcial|fragmento)\)\s*$", "", base)
    return SECCIONES.get(base)


def _iter_bloques(doc) -> Iterator[Paragraph | Table]:
    """Itera párrafos y tablas del documento en el orden real del cuerpo."""
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def _fila_a_texto(seccion: str, headers: list[str], celdas: list[str]) -> str:
    """Convierte una fila de tabla en una frase legible según la sección."""
    campos = {h.strip().lower(): v.strip() for h, v in zip(headers, celdas)}

    if seccion == "Catálogo de productos":
        nombre = campos.get("nombre", "")
        codigo = campos.get("código", campos.get("codigo", ""))
        desc = campos.get("descripción", campos.get("descripcion", "")).rstrip(".")
        disp = campos.get("disponibilidad", "")
        return f"{nombre} ({codigo}): {desc}. Disponibilidad: {disp}."

    if seccion == "Política de descuentos":
        vol = campos.get("volumen del pedido", "")
        dto = campos.get("descuento", "")
        return f"Pedidos de {vol}: {dto} de descuento por volumen."

    # Genérico: "campo: valor; campo: valor"
    return "; ".join(f"{h.strip()}: {v.strip()}" for h, v in zip(headers, celdas) if v.strip())


def cargar_chunks(docx_path: str | Path) -> list[Chunk]:
    """Un chunk por párrafo/ítem de lista y uno por fila de tabla.

    Chunks chicos y focalizados: con e5-small mejoran bastante la separación
    entre "esto está en el doc" y "esto no está".
    """
    doc = docx.Document(str(docx_path))
    chunks: list[Chunk] = []
    seccion_actual: str | None = None

    for bloque in _iter_bloques(doc):
        if isinstance(bloque, Paragraph):
            txt = _norm_ws(bloque.text)
            if not txt:
                continue
            nueva = _match_seccion(txt)
            if nueva:
                seccion_actual = nueva
                continue
            if seccion_actual is None:
                continue  # portada / preámbulo, no nos interesa
            # Prefijo corto con la sección: ayuda a desambiguar ítems sueltos
            # ("Requisitos: ..." solo no dice de qué).
            chunks.append(
                Chunk(seccion=seccion_actual, texto=f"{seccion_actual} — {txt}", tipo="prosa")
            )
        else:  # Table
            filas = [[c.text for c in row.cells] for row in bloque.rows]
            if len(filas) < 2:
                continue
            headers, cuerpo = filas[0], filas[1:]
            seccion = seccion_actual or "Catálogo de productos"
            textos_fila = [_fila_a_texto(seccion, headers, c) for c in cuerpo]
            textos_fila = [t for t in textos_fila if t]
            # Chunk-resumen de la tabla entera: necesario para preguntas del tipo
            # "¿qué productos incluye el catálogo?" / "¿qué descuentos hay?", que
            # necesitan TODAS las filas juntas y con pocas filas puntúan bajo.
            resumen = _resumen_tabla(seccion, textos_fila)
            if resumen:
                chunks.append(Chunk(seccion=seccion, texto=resumen, tipo="tabla"))
            for texto in textos_fila:
                chunks.append(Chunk(seccion=seccion, texto=texto, tipo="tabla"))

    return chunks


def _resumen_tabla(seccion: str, filas: list[str]) -> str:
    if not filas:
        return ""
    if seccion == "Catálogo de productos":
        return "Catálogo de productos: " + " ".join(filas)
    if seccion == "Política de descuentos":
        return "Descuentos por volumen del pedido: " + " ".join(filas)
    return f"{seccion}: " + " ".join(filas)


_WS = re.compile(r"\s+")


def _norm_ws(texto: str) -> str:
    return _WS.sub(" ", texto).strip()
