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

Si dudas entre faq_estatica y con_humano, elige con_humano.
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
        out = llm.create_chat_completion(**kwargs)
        contenido = out["choices"][0]["message"]["content"] or ""
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
