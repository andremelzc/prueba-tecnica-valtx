"""App FastAPI del asistente de consultas comerciales.

Paso 2: en el arranque se carga el LLM local (una sola vez) y se crea el cache
de deduplicación. El endpoint POST /consulta se agrega en el Paso 4; por ahora
hay /health para verificar que la app levanta con `uvicorn main:app --reload`.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import LLM_MODEL_PATH
from app.llm import cargar_llm
from app.normalization import RecentQueryCache
from app.rag import indexar_si_necesario

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("asistente")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cache = RecentQueryCache()

    # El modelo GGUF se carga UNA sola vez acá, no por request.
    if os.getenv("SKIP_LLM") == "1":
        log.warning("SKIP_LLM=1: el LLM no se carga (solo para desarrollo).")
        app.state.llm = None
    else:
        log.info("Cargando LLM local desde %s ...", LLM_MODEL_PATH)
        app.state.llm = cargar_llm()
        log.info("LLM cargado.")

    # Indexado del documento de referencia (una sola vez; si Qdrant ya tiene
    # datos, no reindexa).
    info = indexar_si_necesario()
    log.info("Índice RAG: %s", info)

    yield

    app.state.llm = None


app = FastAPI(title="Asistente de consultas comerciales", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_cargado": getattr(app.state, "llm", None) is not None,
    }
