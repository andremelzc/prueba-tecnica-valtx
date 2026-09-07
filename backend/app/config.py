"""Configuración central: categorías, rutas y umbrales del pipeline.

Todo se puede sobrescribir por variable de entorno para no tener que tocar código
al mover el proyecto a Docker más adelante.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

# --- Rutas -------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"

# Documento de referencia que se indexa una sola vez al iniciar la app.
DOC_REFERENCIA = Path(
    os.getenv("DOC_REFERENCIA", str(DATA_DIR / "documentos_referencia.docx"))
)

# Base de datos SQLite con el registro de consultas.
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(DATA_DIR / "consultas.db")))

# Almacenamiento local de Qdrant (modo embebido: QdrantClient(path=...)).
QDRANT_PATH = Path(os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant")))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "faq_comercial")

# Modelos.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
LLM_MODEL_PATH = Path(
    os.getenv("LLM_MODEL_PATH", str(MODELS_DIR / "Phi-3-mini-4k-instruct-q4.gguf"))
)


# --- Categorías de intención ----------------------------------------------

class Categoria(str, Enum):
    """Categorías de intención que puede devolver el clasificador."""

    FAQ_ESTATICA = "faq_estatica"
    DATO_DINAMICO = "dato_dinamico"
    OTRA_AREA = "otra_area"
    CON_HUMANO = "con_humano"


# Sentinela interno: el clasificador por reglas no pudo decidir y hay que
# pasar la consulta al LLM. Nunca se devuelve al cliente.
AMBIGUO = "ambiguo"

# Orden de prioridad para resolver empates entre reglas.
# Ante la duda preferimos escalar (con_humano) y nunca contestar un dato
# dinámico con el modelo (dato_dinamico va segundo).
PRIORIDAD_CATEGORIAS: tuple[Categoria, ...] = (
    Categoria.CON_HUMANO,
    Categoria.DATO_DINAMICO,
    Categoria.OTRA_AREA,
    Categoria.FAQ_ESTATICA,
)


# --- Umbrales --------------------------------------------------------------

# Casi-duplicados: ratio de rapidfuzz (0-100) a partir del cual dos consultas
# se consideran la misma.
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "90"))
# Ventana de "consultas recientes" para comparar duplicados.
DEDUP_MAX_ITEMS = int(os.getenv("DEDUP_MAX_ITEMS", "50"))
DEDUP_TTL_SECONDS = int(os.getenv("DEDUP_TTL_SECONDS", "1800"))  # 30 min

# RAG: score mínimo de similitud (coseno, 0-1) para fiarnos de un chunk.
# Por debajo de esto no inventamos: la consulta cae a con_humano.
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.80"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
