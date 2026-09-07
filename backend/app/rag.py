"""RAG sobre `documentos_referencia.docx`: indexado + búsqueda + generación.

- `indexar_si_necesario()`  -> se llama una vez al iniciar la app. Si la colección
  de Qdrant ya tiene puntos, no reindexa.
- `responder_faq(texto, llm)` -> para consultas clasificadas como faq_estatica:
    1. embedding de la consulta + top-3 en Qdrant
    2. si el mejor score < umbral -> NO llama al LLM, cae a con_humano
       (`rag_baja_confianza`)
    3. si supera el umbral -> el LLM responde SOLO con los chunks y cita la
       sección; si no puede fundamentarlo -> cae a con_humano (`rag_sin_fundamento`)

Embeddings: intfloat/multilingual-e5-small (requiere prefijos "query:"/"passage:").
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Optional

from .config import (
    DOC_REFERENCIA,
    EMBEDDING_MODEL,
    QDRANT_COLLECTION,
    QDRANT_PATH,
    RAG_SCORE_THRESHOLD,
    RAG_TOP_K,
    Categoria,
)
from .indexing import cargar_chunks

_EMB_DIM = 384  # e5-small

_embedder: Any = None
_qdrant: Any = None
_lock = threading.Lock()

# marcador que el LLM debe emitir si el contexto no alcanza para responder
_SIN_FUNDAMENTO = "NO_FUNDAMENTADO"


# --- Singletons -----------------------------------------------------------

def get_embedder() -> Any:
    global _embedder
    with _lock:
        if _embedder is None:
            from sentence_transformers import SentenceTransformer

            _embedder = SentenceTransformer(EMBEDDING_MODEL)
        return _embedder


def get_qdrant() -> Any:
    global _qdrant
    with _lock:
        if _qdrant is None:
            from qdrant_client import QdrantClient

            QDRANT_PATH.mkdir(parents=True, exist_ok=True)
            _qdrant = QdrantClient(path=str(QDRANT_PATH))
        return _qdrant


def _embed(textos: list[str], *, prefijo: str) -> list[list[float]]:
    model = get_embedder()
    vecs = model.encode(
        [f"{prefijo}: {t}" for t in textos],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return vecs.tolist()


# --- Indexado -----------------------------------------------------------

def indexar_si_necesario(force: bool = False) -> dict:
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = get_qdrant()
    existe = client.collection_exists(QDRANT_COLLECTION)
    if existe and not force:
        n = client.count(QDRANT_COLLECTION).count
        if n > 0:
            return {"reindexado": False, "chunks": n}

    chunks = cargar_chunks(DOC_REFERENCIA)
    vectores = _embed([c.texto for c in chunks], prefijo="passage")

    if existe:
        client.delete_collection(QDRANT_COLLECTION)
    client.create_collection(
        QDRANT_COLLECTION,
        vectors_config=VectorParams(size=_EMB_DIM, distance=Distance.COSINE),
    )
    client.upsert(
        QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=i,
                vector=vectores[i],
                payload={"seccion": c.seccion, "texto": c.texto, "tipo": c.tipo},
            )
            for i, c in enumerate(chunks)
        ],
    )
    return {"reindexado": True, "chunks": len(chunks)}


# --- Búsqueda ----------------------------------------------------------

@dataclass
class Hit:
    seccion: str
    texto: str
    score: float


def buscar(texto_consulta: str, k: int = RAG_TOP_K) -> list[Hit]:
    client = get_qdrant()
    qvec = _embed([texto_consulta], prefijo="query")[0]
    res = client.query_points(QDRANT_COLLECTION, query=qvec, limit=k, with_payload=True)
    return [
        Hit(seccion=p.payload["seccion"], texto=p.payload["texto"], score=float(p.score))
        for p in res.points
    ]


# --- Generación --------------------------------------------------------

@dataclass
class RespuestaRAG:
    categoria: Categoria
    respuesta: str
    fuente: Optional[str]
    confianza: float
    metodo: str  # "rag" | "rag_baja_confianza" | "rag_sin_fundamento"
    hits: list[Hit]


_SYSTEM_RAG = """\
Eres un asistente de consultas comerciales. Respondes SOLO con la información del \
CONTEXTO que se te da (extractos de la documentación interna).

Reglas:
- Si el CONTEXTO no contiene la respuesta, responde exactamente: NO_FUNDAMENTADO
- Usa ÚNICAMENTE datos que estén literalmente en el CONTEXTO. No agregues pasos,
  ejemplos, campos ni detalles que no aparezcan escritos. No uses conocimiento externo.
- Respuesta de 1 o 2 frases, en español, sin listas ni numeraciones.
- Termina citando la sección entre paréntesis, así: (Fuente: <sección>)\
"""

# Compuerta previa: ¿el contexto alcanza para responder? Respuesta forzada SI/NO.
_SYSTEM_GATE = """\
Decides si el CONTEXTO responde de forma directa y completa la PREGUNTA.

- Responde NO si el CONTEXTO no menciona el tema, o solo lo roza sin dar el dato concreto.
- Responde NO si la PREGUNTA pide una opinión, una recomendación, o un dato que no aparece.
- Responde NO si la PREGUNTA es un saludo o algo vago sin una consulta concreta.
- Responde SI solo si la respuesta se puede extraer textualmente del CONTEXTO.

Responde únicamente con SI o NO.\
"""
_GATE_GBNF = 'root ::= "SI" | "NO"\n'
_gate_grammar: Any = None

# Backstop: frases típicas de Phi-3 cuando en realidad NO puede fundamentar
# (no emite el marcador y la compuerta a veces lo deja pasar).
_NEG_RE = re.compile(
    "|".join([
        r"\bno\s+hay\s+(informaci|datos|detalles|nada)",
        r"\bno\s+(se\s+)?(menciona|indica|especifica|detalla|precisa|aclara|dice|figura|"
        r"aparece|incluye|contiene|proporciona|responde|encuentra)\w*",
        r"\bno\s+(se\s+)?(puede|podemos|es\s+posible)\s+(determinar|responder|confirmar|saber|precisar)",
        r"\b(informaci[oó]n|contexto|documento|secci[oó]n|texto)\b[^.]{0,50}\bno\b[^.]{0,50}"
        r"\b(menciona|indica|especifica|incluye|contiene|responde|detalla|aparece|permite)",
        r"\bnecesitar[ií]a\s+m[aá]s\s+(informaci[oó]n|detalles|contexto)",
        r"\bno\s+(figura|est[aá])\b[^.]{0,40}\b(context|document|informaci)",
    ]),
    re.IGNORECASE,
)


def _get_gate_grammar() -> Any:
    global _gate_grammar
    if _gate_grammar is None:
        from llama_cpp import LlamaGrammar

        _gate_grammar = LlamaGrammar.from_string(_GATE_GBNF, verbose=False)
    return _gate_grammar


def _construir_contexto(hits: list[Hit]) -> str:
    return "\n".join(f"[sección: {h.seccion}] {h.texto}" for h in hits)


_CORTE_RE = re.compile(r"\n\s*(CONTEXTO|PREGUNTA|---|\Z)", re.IGNORECASE)
_FRASE_RE = re.compile(r"(?<=[.!?])\s+")


_LISTA_COLGANDO_RE = re.compile(r"(?:\n+\s*\d+[.)]\s*)+$")


def _limpiar_respuesta(texto: str, limite: int = 400) -> str:
    """Corta divagues del modelo: si intenta continuar el prompt, o si se pasa."""
    texto = _CORTE_RE.split(texto, maxsplit=1)[0].strip()
    if len(texto) > limite:
        recorte = texto[:limite]
        fin = recorte.rfind(".")
        texto = (recorte[: fin + 1] if fin > 100 else recorte).strip()
    # ítem de lista iniciado y sin contenido ("...\n4.")
    texto = _LISTA_COLGANDO_RE.sub("", texto).strip()
    return texto


def _es_deflexion(texto: str) -> bool:
    """El LLM no fundamentó la respuesta (aunque no haya emitido el marcador)."""
    if _SIN_FUNDAMENTO in texto.upper() or len(texto) < 3:
        return True
    # Solo miramos la 1ª frase: si la respuesta abre con una negativa sobre el
    # contexto, es una deflexión; si abre con la respuesta y aclara un matiz
    # después ("...No se menciona garantía extendida"), la damos por válida.
    primera = _FRASE_RE.split(texto, maxsplit=1)[0]
    return bool(_NEG_RE.search(primera))


def _contexto_suficiente(llm: Any, contexto: str, pregunta: str) -> bool:
    try:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_GATE},
                {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"},
            ],
            temperature=0.0,
            max_tokens=4,
            grammar=_get_gate_grammar(),
        )
        return (out["choices"][0]["message"]["content"] or "").strip().upper().startswith("SI")
    except Exception:
        return False


def responder_faq(texto_consulta: str, llm: Any) -> RespuestaRAG:
    hits = buscar(texto_consulta, k=RAG_TOP_K)
    mejor = hits[0].score if hits else 0.0

    # 6. Umbral de confianza: por debajo, no se llama al LLM.
    if not hits or mejor < RAG_SCORE_THRESHOLD:
        return RespuestaRAG(
            categoria=Categoria.CON_HUMANO,
            respuesta=(
                "No encontré esta información en la documentación de referencia. "
                "Derivo tu consulta al equipo comercial."
            ),
            fuente=None,
            confianza=round(mejor, 3),
            metodo="rag_baja_confianza",
            hits=hits,
        )

    contexto = _construir_contexto(hits)

    # 7a. Compuerta: ¿el contexto realmente permite responder? (el score de e5 es
    #     poco discriminante, así que esto es el filtro fino).
    if not _contexto_suficiente(llm, contexto, texto_consulta):
        return RespuestaRAG(
            categoria=Categoria.CON_HUMANO,
            respuesta=(
                "No encontré esta información en la documentación de referencia. "
                "Derivo tu consulta al equipo comercial."
            ),
            fuente=None,
            confianza=round(mejor, 3),
            metodo="rag_sin_fundamento",
            hits=hits,
        )

    # 7b. Generación fundamentada en los chunks recuperados.
    try:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_RAG},
                {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {texto_consulta}"},
            ],
            temperature=0.0,
            max_tokens=160,
        )
        texto = _limpiar_respuesta((out["choices"][0]["message"]["content"] or "").strip())
    except Exception as exc:
        return RespuestaRAG(
            categoria=Categoria.CON_HUMANO,
            respuesta="No pude generar una respuesta fundamentada. Derivo al equipo comercial.",
            fuente=None,
            confianza=round(mejor, 3),
            metodo="rag_sin_fundamento",
            hits=hits,
        )

    if _es_deflexion(texto):
        return RespuestaRAG(
            categoria=Categoria.CON_HUMANO,
            respuesta=(
                "No encontré esta información en la documentación de referencia. "
                "Derivo tu consulta al equipo comercial."
            ),
            fuente=None,
            confianza=round(mejor, 3),
            metodo="rag_sin_fundamento",
            hits=hits,
        )

    fuente = hits[0].seccion
    if "fuente" not in texto.lower():  # el modelo no siempre añade la cita
        texto = f"{texto} (Fuente: {fuente})"

    return RespuestaRAG(
        categoria=Categoria.FAQ_ESTATICA,
        respuesta=texto,
        fuente=fuente,
        confianza=round(mejor, 3),
        metodo="rag",
        hits=hits,
    )
