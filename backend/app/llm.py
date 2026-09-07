"""Wrapper del LLM local (llama-cpp-python) + clasificación de intención por LLM.

- El modelo GGUF se carga UNA sola vez (`cargar_llm`) y queda cacheado en un
  singleton de módulo. `main.py` lo llama en el lifespan y además lo deja en
  `app.state.llm`.
- `clasificar_intencion_llm(texto)` es el fallback que usa el clasificador cuando
  las reglas devuelven AMBIGUO: arma un prompt con la descripción de las 4
  categorías, pide un JSON `{"categoria": ..., "razon": ...}` y lo parsea.
- Si el LLM alucina una categoría o el JSON no parsea, NO se rompe nada: se cae a
  `con_humano` con método `llm_fallback_error` (escalar de más > responder mal).
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .config import LLM_MODEL_PATH, Categoria

# --- Carga del modelo (singleton) ---------------------------------------

_llm: Any = None
_lock = threading.Lock()


def cargar_llm(model_path: Optional[Path] = None, **overrides: Any) -> Any:
    """Carga el modelo GGUF una sola vez y devuelve la instancia `Llama`.

    Idempotente: llamadas siguientes devuelven la instancia ya cargada.
    """
    global _llm
    with _lock:
        if _llm is not None:
            return _llm

        from llama_cpp import Llama

        ruta = Path(model_path or LLM_MODEL_PATH)
        if not ruta.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo GGUF en {ruta}. "
                "Descárgalo con: python -m scripts.descargar_modelo"
            )

        params: dict[str, Any] = dict(
            model_path=str(ruta),
            n_ctx=int(os.getenv("LLM_N_CTX", "4096")),
            n_threads=int(os.getenv("LLM_N_THREADS", str(os.cpu_count() or 4))),
            n_gpu_layers=int(os.getenv("LLM_N_GPU_LAYERS", "0")),
            verbose=False,
        )
        # Por defecto dejamos que llama-cpp deduzca el formato de chat desde el
        # template embebido en el GGUF (Phi-3 lo trae). Se puede forzar con
        # LLM_CHAT_FORMAT (p. ej. "chatml") si hiciera falta.
        chat_format = os.getenv("LLM_CHAT_FORMAT", "").strip()
        if chat_format:
            params["chat_format"] = chat_format
        params.update(overrides)
        _llm = Llama(**params)
        return _llm


def get_llm() -> Any:
    """Devuelve el LLM ya cargado (o lo carga on-demand como último recurso)."""
    return _llm if _llm is not None else cargar_llm()


# llama-cpp no es thread-safe para inferencia concurrente sobre el mismo
# contexto; FastAPI corre los endpoints sync en un threadpool, así que
# serializamos las generaciones.
_infer_lock = threading.Lock()


def chat_completion(llm: Any, **kwargs: Any) -> str:
    """`create_chat_completion` serializado. Devuelve el texto de la respuesta."""
    with _infer_lock:
        out = llm.create_chat_completion(**kwargs)
    return out["choices"][0]["message"]["content"] or ""


def reset_llm() -> None:
    """Libera el singleton (para tests)."""
    global _llm
    with _lock:
        _llm = None


# --- Clasificación de intención por LLM --------------------------------

_CATEGORIAS_VALIDAS = {c.value for c in Categoria}

# Gramática GBNF: obliga al modelo a emitir EXACTAMENTE
# {"categoria": <una de las 4>, "razon": "<texto>"}.
# Phi-3-mini por sí solo no respeta el esquema (inventa "intent"/"command"/...),
# así que la gramática es lo que hace el parseo confiable.
_GRAMMAR_GBNF = r'''
root   ::= "{" ws "\"categoria\"" ws ":" ws cat ws "," ws "\"razon\"" ws ":" ws str ws "}"
cat    ::= "\"faq_estatica\"" | "\"dato_dinamico\"" | "\"otra_area\"" | "\"con_humano\""
str    ::= "\"" ([^"\\\n] | "\\" .){0,90} "\""
ws     ::= [ \t\n]*
'''

_grammar: Any = None


def _get_grammar() -> Any:
    global _grammar
    if _grammar is None:
        from llama_cpp import LlamaGrammar

        _grammar = LlamaGrammar.from_string(_GRAMMAR_GBNF, verbose=False)
    return _grammar


_SYSTEM_CLASIFICACION = """\
Eres un clasificador de intención de un asistente de consultas comerciales.
Clasifica la consulta del usuario en EXACTAMENTE UNA de estas 4 categorías:

- faq_estatica: se puede responder con la documentación de referencia interna:
  cómo solicitar un producto o servicio, formulario F-01, plazos, política de
  devoluciones y garantía, política de descuentos por volumen, catálogo de
  productos, cómo cancelar o modificar una solicitud.
- dato_dinamico: pide un dato que cambia y vive en el sistema comercial y NO en
  la documentación: precio, stock/disponibilidad, promociones vigentes, tipo de
  cambio, fecha del próximo lote, si un precio "sigue igual".
- otra_area: está fuera del alcance comercial: RRHH (sueldos, vacaciones,
  recursos humanos), TI (contraseñas, accesos, laptop, soporte técnico interno),
  u otros servicios internos (comedor).
- con_humano: excepción, queja o reclamo, negociación, caso especial que necesita
  criterio humano: descuentos fuera de tabla, devolución fuera de plazo,
  reembolsos no estándar, cotización a medida, cambio de proveedor, "quiero
  hablar con alguien".

Si la consulta PIDE INFORMACIÓN sobre productos, servicios, condiciones de
compra, pagos, envíos o soporte —aunque no sepas si está documentada— elige
faq_estatica: un filtro posterior valida si la respuesta está en la documentación
y, si no, la deriva. Reserva con_humano para quejas, reclamos, negociaciones o
pedidos EXPLÍCITOS de excepción o de hablar con una persona.
Si dudas entre faq_estatica y dato_dinamico, elige dato_dinamico.

Responde ÚNICAMENTE con un objeto JSON, sin texto adicional, con esta forma exacta:
{"categoria": "<una de: faq_estatica, dato_dinamico, otra_area, con_humano>", "razon": "<motivo breve, máx 15 palabras>"}

Ejemplos:
Consulta: "¿cuánto cuesta el producto alfa?" -> {"categoria": "dato_dinamico", "razon": "pregunta por un precio"}
Consulta: "¿cómo pido un producto del catálogo?" -> {"categoria": "faq_estatica", "razon": "procedimiento de solicitud, está en la doc"}
Consulta: "¿cómo solicito mis vacaciones?" -> {"categoria": "otra_area", "razon": "tema de RRHH"}
Consulta: "quiero un reembolso fuera de plazo" -> {"categoria": "con_humano", "razon": "excepción a la política"}
"""


@dataclass
class LLMClasificacion:
    categoria: Categoria
    razon: str
    metodo: str  # "llm" | "llm_fallback_error"


def _extraer_json(texto: str) -> Optional[dict]:
    """Intenta parsear el primer objeto JSON que aparezca en la respuesta."""
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def clasificar_intencion_llm(texto_normalizado: str, llm: Any = None) -> LLMClasificacion:
    """Fallback de clasificación: pide al LLM elegir una de las 4 categorías."""
    # Con el modelo real (llm=None) usamos gramática GBNF; los tests inyectan un
    # LLM falso que no la soporta.
    usar_gramatica = llm is None
    llm = llm or get_llm()
    try:
        kwargs: dict[str, Any] = dict(
            messages=[
                {"role": "system", "content": _SYSTEM_CLASIFICACION},
                {"role": "user", "content": f'Consulta: "{texto_normalizado}"'},
            ],
            temperature=0.0,
            # Holgado: la gramática ya acota la razón a ~90 chars; damos margen
            # de sobra para que el JSON siempre cierre.
            max_tokens=256,
        )
        if usar_gramatica:
            kwargs["grammar"] = _get_grammar()
        contenido = chat_completion(llm, **kwargs)
    except Exception as exc:  # el LLM falló al generar
        return LLMClasificacion(
            categoria=Categoria.CON_HUMANO,
            razon=f"error del LLM: {exc}",
            metodo="llm_fallback_error",
        )

    data = _extraer_json(contenido)
    categoria = (data or {}).get("categoria")
    if not isinstance(categoria, str) or categoria.strip().lower() not in _CATEGORIAS_VALIDAS:
        return LLMClasificacion(
            categoria=Categoria.CON_HUMANO,
            razon=f"respuesta no parseable o categoría inválida: {contenido[:120]!r}",
            metodo="llm_fallback_error",
        )

    razon = ""
    if isinstance(data, dict) and isinstance(data.get("razon"), str):
        razon = data["razon"].strip()[:200]

    return LLMClasificacion(
        categoria=Categoria(categoria.strip().lower()),
        razon=razon or "(sin razón)",
        metodo="llm",
    )


# --- Resumen para casos con_humano -----------------------------------

_SYSTEM_RESUMEN = """\
Tu tarea es RESUMIR, no responder. A partir de la consulta de un cliente, escribe
UNA sola frase (máximo 25 palabras), en tercera persona, que le sirva a una
persona del equipo comercial para saber qué necesita o reclama el cliente.

Prohibido: saludar, responder al cliente, dar instrucciones o pasos, usar listas,
escribir la palabra "Resumen".

Ejemplos:
Consulta: "quiero que me devuelvan toda la plata aunque ya usé el producto"
Resumen: El cliente pide el reembolso total de un producto que ya usó, fuera de la política estándar.
Consulta: "necesito que me hagan un descuento más grande que el de la tabla para una compra grande"
Resumen: El cliente solicita un descuento mayor al de la política para una compra de gran volumen.\
"""

_RESUMEN_PREFIJO_RE = re.compile(r"^\s*(resumen|el resumen (es|sería))\s*[:\-]?\s*", re.IGNORECASE)
_RESUMEN_CORTE_RE = re.compile(r"[\n\r]|\s\d+[.)]\s|\s-\s")


def generar_resumen_con_humano(texto_normalizado: str, llm: Any = None) -> str:
    """Resumen de UNA frase de la consulta, para quien la va a atender."""
    llm = llm or get_llm()
    try:
        crudo = chat_completion(
            llm,
            messages=[
                {"role": "system", "content": _SYSTEM_RESUMEN},
                {"role": "user", "content": f'Consulta: "{texto_normalizado}"\nResumen:'},
            ],
            temperature=0.0,
            max_tokens=60,
        ).strip()
    except Exception:
        crudo = ""

    # Nos quedamos con la 1ª línea / 1ª frase; cortamos si arranca a divagar.
    crudo = _RESUMEN_PREFIJO_RE.sub("", crudo.strip())
    resumen = _RESUMEN_CORTE_RE.split(crudo, maxsplit=1)[0].strip().strip('"')
    if "." in resumen:
        resumen = resumen.split(".", 1)[0].strip() + "."
    # Fallback: la consulta tal cual (recortada) si no salió nada útil.
    if len(resumen) < 10:
        resumen = texto_normalizado[:200].strip()
    return resumen[:280]
