"""Pruebas de la Parte 2 (fallback de clasificación al LLM), con un LLM falso.

No necesita el modelo GGUF: inyecta un objeto que imita `create_chat_completion`
para verificar el parseo y, sobre todo, el manejo de errores (categoría inválida
o inventada / JSON malformado -> con_humano + llm_fallback_error).

    python -m scripts.test_parte2
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import clasificar  # noqa: E402
from app.config import Categoria  # noqa: E402
from app.llm import LLMClasificacion, clasificar_intencion_llm  # noqa: E402
from app.normalization import normalizar  # noqa: E402

_fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"[{'ok  ' if cond else 'FALLA'}] {msg}")
    if not cond:
        _fallos.append(msg)


class FakeLlm:
    """Imita lo justo de llama_cpp.Llama: devuelve un contenido fijo."""

    def __init__(self, contenido: str | Exception):
        self._contenido = contenido

    def create_chat_completion(self, **_kwargs):
        if isinstance(self._contenido, Exception):
            raise self._contenido
        return {"choices": [{"message": {"content": self._contenido}}]}


CASOS = [
    # (respuesta cruda del LLM, categoria esperada, metodo esperado)
    ('{"categoria": "dato_dinamico", "razon": "pregunta por precio"}', Categoria.DATO_DINAMICO, "llm"),
    ('  {"categoria":"otra_area","razon":"es de RRHH"}  ', Categoria.OTRA_AREA, "llm"),
    ('Claro: {"categoria": "faq_estatica", "razon": "x"} listo', Categoria.FAQ_ESTATICA, "llm"),
    ('{"categoria": "FAQ_ESTATICA"}', Categoria.FAQ_ESTATICA, "llm"),  # case-insensitive
    # --- errores: deben caer a con_humano ---
    ('{"categoria": "reclamo_urgente", "razon": "inventada"}', Categoria.CON_HUMANO, "llm_fallback_error"),
    ('no soy un json', Categoria.CON_HUMANO, "llm_fallback_error"),
    ('{"categoria": 42}', Categoria.CON_HUMANO, "llm_fallback_error"),
    ('{"razon": "olvidó la categoria"}', Categoria.CON_HUMANO, "llm_fallback_error"),
]

for crudo, cat_esp, metodo_esp in CASOS:
    res = clasificar_intencion_llm("texto de prueba", llm=FakeLlm(crudo))
    check(res.categoria == cat_esp and res.metodo == metodo_esp,
          f"{crudo[:45]!r:<48} -> {res.categoria.value}/{res.metodo}")

# excepción al generar
res = clasificar_intencion_llm("x", llm=FakeLlm(RuntimeError("boom")))
check(res.categoria == Categoria.CON_HUMANO and res.metodo == "llm_fallback_error",
      "excepción del LLM -> con_humano/llm_fallback_error")

# integración con el clasificador: consulta ambigua + llm_fn
res = clasificar(normalizar("¿Eso se puede?"),
                 llm_fn=lambda t: clasificar_intencion_llm(t, llm=FakeLlm('{"categoria":"con_humano","razon":"vago"}')))
check(res.categoria == Categoria.CON_HUMANO and res.metodo == "llm",
      "clasificar() delega en el LLM cuando las reglas dan AMBIGUO")

# consulta clara: NO debe llamar al LLM
def _no_llamar(_t):
    raise AssertionError("no debería llamar al LLM")

res = clasificar(normalizar("¿Cuál es el precio actual del Producto Alfa?"), llm_fn=_no_llamar)
check(res.categoria == Categoria.DATO_DINAMICO and res.metodo == "regla",
      "clasificar() NO llama al LLM cuando las reglas deciden")

print()
if _fallos:
    print(f"FALLA: {len(_fallos)} fallo(s)")
    sys.exit(1)
print("OK: todo verde")
