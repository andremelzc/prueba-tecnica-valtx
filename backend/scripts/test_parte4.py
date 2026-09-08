"""Pruebas de la Parte 4 (endpoint + SQLite + resumen con_humano).

No necesita el modelo GGUF: usa SKIP_LLM=1 para el endpoint y dobles para la
lógica de pipeline que toca el LLM.

    python -m scripts.test_parte4
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# BD temporal y sin LLM: hay que fijarlo ANTES de importar app.*
_TMP_DB = Path(tempfile.gettempdir()) / "test_parte4_consultas.db"
_TMP_DB.unlink(missing_ok=True)
os.environ["SQLITE_PATH"] = str(_TMP_DB)
os.environ["SKIP_LLM"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app import db  # noqa: E402
from app.config import Categoria  # noqa: E402
from app.normalization import RecentQueryCache, normalizar  # noqa: E402
from app.pipeline import procesar_consulta  # noqa: E402
from app.rag import Hit, RespuestaRAG  # noqa: E402

_fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"[{'ok  ' if cond else 'FALLA'}] {msg}")
    if not cond:
        _fallos.append(msg)


# --- pipeline: resumen para con_humano (con dobles) -------------------

def _fake_llm_fn(_t):
    from app.llm import LLMClasificacion
    return LLMClasificacion(categoria=Categoria.CON_HUMANO, razon="vago", metodo="llm")


def _fake_faq_deriva(_t):
    return RespuestaRAG(
        categoria=Categoria.CON_HUMANO, respuesta="No está en el doc.", fuente=None,
        confianza=0.5, metodo="rag_baja_confianza", hits=[],
    )


def _fake_faq_ok(_t):
    return RespuestaRAG(
        categoria=Categoria.FAQ_ESTATICA, respuesta="La garantía es 12 meses. (Fuente: FAQ)",
        fuente="Preguntas frecuentes", confianza=0.9, metodo="rag", hits=[],
    )


resumen_calls: list[str] = []
def _fake_resumen(t):
    resumen_calls.append(t)
    return f"RESUMEN: {t[:40]}"


cache = RecentQueryCache()

# queja directa (regla) -> con_humano + resumen
r = procesar_consulta("Tengo una queja sobre la atención", "chat",
                      cache=cache, llm_fn=_fake_llm_fn, faq_fn=_fake_faq_ok, resumen_fn=_fake_resumen)
check(r.categoria == Categoria.CON_HUMANO and r.resumen and r.resumen.startswith("RESUMEN:"),
      "con_humano por regla -> lleva resumen del LLM")

# faq que el RAG deriva -> con_humano + resumen
r = procesar_consulta("¿hacen envíos a marte?", "chat",
                      cache=cache, llm_fn=_fake_llm_fn, faq_fn=_fake_faq_deriva, resumen_fn=_fake_resumen)
check(r.categoria == Categoria.CON_HUMANO and r.metodo_clasificacion == "rag_baja_confianza" and r.resumen,
      "con_humano por derivación del RAG -> también lleva resumen")

# faq respondida por RAG -> NO resumen, mantiene método de clasificación
r = procesar_consulta("¿cuánto dura la garantía?", "chat",
                      cache=cache, llm_fn=_fake_llm_fn, faq_fn=_fake_faq_ok, resumen_fn=_fake_resumen)
check(r.categoria == Categoria.FAQ_ESTATICA and r.resumen is None and r.metodo_clasificacion == "regla",
      "faq_estatica respondida por RAG -> sin resumen, método 'regla'")

# dato_dinamico -> mensaje fijo, sin resumen, sin tocar el LLM de resumen
n_antes = len(resumen_calls)
r = procesar_consulta("¿cuál es el precio del Producto Alfa?", "correo",
                      cache=cache, llm_fn=_fake_llm_fn, faq_fn=_fake_faq_ok, resumen_fn=_fake_resumen)
check(r.categoria == Categoria.DATO_DINAMICO and "sistema comercial" in r.respuesta and r.resumen is None,
      "dato_dinamico -> mensaje fijo, sin resumen")
check(len(resumen_calls) == n_antes, "dato_dinamico no invoca el generador de resumen")


# --- SQLite ----------------------------------------------------------

db.init_db()
n0 = db.contar()
from app.schemas import ConsultaRequest, ConsultaResponse  # noqa: E402

rid = db.registrar_consulta(
    ConsultaRequest(texto="hola", canal="chat"),
    ConsultaResponse(categoria=Categoria.CON_HUMANO, respuesta="derivado", confianza=0.3,
                     metodo_clasificacion="llm", es_duplicado=False, resumen="RESUMEN: hola"),
)
check(isinstance(rid, int) and db.contar() == n0 + 1, "registrar_consulta inserta una fila")


# --- endpoint (SKIP_LLM=1) -----------------------------------------

client = TestClient(main.app)
with client:
    n_db = db.contar()

    resp = client.post("/consulta", json={"texto": "¿Cuál es el plazo para devolver un producto?", "canal": "chat"})
    check(resp.status_code == 200, f"POST /consulta -> 200 ({resp.status_code})")
    body = resp.json()
    check({"categoria", "respuesta", "fuente", "confianza", "metodo_clasificacion", "es_duplicado"}
          <= set(body), f"la respuesta trae los campos del contrato ({sorted(body)})")
    check(body["categoria"] == "faq_estatica", f"clasificada como faq_estatica ({body['categoria']})")
    check(db.contar() == n_db + 1, "la consulta quedó registrada en SQLite")

    # misma consulta (casi igual) -> duplicado, se registra igual
    resp2 = client.post("/consulta", json={"texto": "cual es el plazo para devolver un producto", "canal": "correo"})
    check(resp2.status_code == 200 and resp2.json()["es_duplicado"] is True,
          "reenvío casi-idéntico -> es_duplicado=true")
    check(db.contar() == n_db + 2, "el duplicado también se registra en SQLite")

    # otra_area
    resp3 = client.post("/consulta", json={"texto": "¿Cuándo pagan los sueldos este mes?", "canal": "chat"})
    check(resp3.json()["categoria"] == "otra_area", "consulta de RRHH -> otra_area")

_TMP_DB.unlink(missing_ok=True)
print()
if _fallos:
    print(f"FALLA: {len(_fallos)} fallo(s)")
    sys.exit(1)
print("OK: todo verde")
