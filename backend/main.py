"""App FastAPI del asistente de consultas comerciales.

En el arranque (una sola vez): se carga el LLM local, se indexa el documento de
referencia en Qdrant y se crea la tabla de SQLite.

El endpoint `POST /consulta` solo orquesta: normaliza/clasifica/responde vía
`app.pipeline.procesar_consulta` y persiste el resultado con `app.db`.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import LLM_MODEL_PATH
from app.llm import cargar_llm, clasificar_intencion_llm, generar_resumen_con_humano, get_llm
from app.normalization import RecentQueryCache
from app.pipeline import procesar_consulta
from app.rag import indexar_si_necesario, responder_faq
from app.schemas import ConsultaRequest, ConsultaResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("asistente")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cache = RecentQueryCache()
    db.init_db()

    # El modelo GGUF se carga UNA sola vez acá, no por request.
    if os.getenv("SKIP_LLM") == "1":
        log.warning("SKIP_LLM=1: el LLM no se carga (solo para desarrollo).")
        app.state.llm = None
    else:
        log.info("Cargando LLM local desde %s ...", LLM_MODEL_PATH)
        app.state.llm = cargar_llm()
        log.info("LLM cargado.")
        # Indexado del documento (idempotente: si Qdrant ya tiene datos, no reindexa).
        log.info("Índice RAG: %s", indexar_si_necesario())

    yield

    app.state.llm = None


app = FastAPI(title="Asistente de consultas comerciales", lifespan=lifespan)

# CORS abierto por ahora; se restringe cuando se sepa el origen del frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_cargado": getattr(app.state, "llm", None) is not None,
        "consultas_registradas": db.contar(),
    }


@app.post("/consulta", response_model=ConsultaResponse)
def consulta(req: ConsultaRequest) -> ConsultaResponse:
    llm_disponible = getattr(app.state, "llm", None) is not None

    llm_fn = clasificar_intencion_llm if llm_disponible else None
    faq_fn = (lambda t: responder_faq(t, get_llm())) if llm_disponible else None
    resumen_fn = (lambda t: generar_resumen_con_humano(t, get_llm())) if llm_disponible else None

    resp = procesar_consulta(
        req.texto,
        req.canal,
        cache=app.state.cache,
        llm_fn=llm_fn,
        faq_fn=faq_fn,
        resumen_fn=resumen_fn,
    )

    # Cada llamada se registra, sea o no duplicado, sea cual sea la categoría.
    db.registrar_consulta(req, resp)
    return resp


# Si hay un build del frontend junto al backend (Docker), lo sirve desde el mismo
# origen. Se monta al final para no tapar /consulta, /health ni /docs.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")
    log.info("Sirviendo frontend desde %s", _STATIC_DIR)
