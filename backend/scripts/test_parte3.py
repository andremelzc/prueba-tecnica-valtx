"""Pruebas de la Parte 3 (RAG) que no necesitan el modelo ni Qdrant.

- `cargar_chunks`: parseo del .docx (párrafos + tablas, secciones correctas).
- `responder_faq`: lógica de umbral y compuerta, con `buscar` y el LLM simulados.

    python -m scripts.test_parte3
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import rag  # noqa: E402
from app.config import DOC_REFERENCIA, Categoria  # noqa: E402
from app.indexing import cargar_chunks  # noqa: E402

_fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"[{'ok  ' if cond else 'FALLA'}] {msg}")
    if not cond:
        _fallos.append(msg)


# --- indexing ------------------------------------------------------------

chunks = cargar_chunks(DOC_REFERENCIA)
secciones = {c.seccion for c in chunks}
esperadas = {
    "Catálogo de productos",
    "Cómo solicitar un producto o servicio",
    "Política de devoluciones y garantías",
    "Política de descuentos",
    "Preguntas frecuentes",
}
check(secciones == esperadas, f"5 secciones canónicas detectadas ({sorted(secciones)})")
tabla = [c for c in chunks if c.tipo == "tabla"]
check(len(tabla) == 7, f"7 chunks de tabla: 5 filas + 2 resúmenes ({len(tabla)})")
check(any("COD-ALF" in c.texto for c in chunks), "el catálogo (tabla) llegó a los chunks")
check(any(c.texto.startswith("Catálogo de productos:") and "COD-GAM" in c.texto for c in tabla),
      "hay un chunk-resumen del catálogo con las 3 líneas")
check(any("15 días" in c.texto or "15 dias" in c.texto for c in chunks), "plazo de devolución presente")
check(any("50 unidades" in c.texto and "5 %" in c.texto for c in chunks), "fila de descuento legible")


# --- responder_faq: umbral y compuerta (con dobles) --------------------

class FakeLlm:
    def __init__(self, gate: str, answer: str = ""):
        self._gate, self._answer = gate, answer
        self.calls = 0

    def create_chat_completion(self, **kw):
        self.calls += 1
        # 1ª llamada = compuerta SI/NO; 2ª = generación
        contenido = self._gate if self.calls == 1 else self._answer
        return {"choices": [{"message": {"content": contenido}}]}


def _hits(score):
    return [rag.Hit(seccion="Política de devoluciones y garantías", texto="Garantía: 12 meses.", score=score)]


def _run(monkey_score, gate, answer=""):
    orig = rag.buscar
    rag.buscar = lambda q, k=3: _hits(monkey_score)
    try:
        return rag.responder_faq("pregunta", FakeLlm(gate, answer))
    finally:
        rag.buscar = orig


r = _run(0.70, "SI", "cualquier cosa")
check(r.categoria == Categoria.CON_HUMANO and r.metodo == "rag_baja_confianza",
      "score por debajo del umbral -> con_humano/rag_baja_confianza (sin llamar al LLM)")

r = _run(0.90, "NO")
check(r.categoria == Categoria.CON_HUMANO and r.metodo == "rag_sin_fundamento",
      "compuerta dice NO -> con_humano/rag_sin_fundamento")

r = _run(0.90, "SI", "La garantía es de 12 meses. (Fuente: Política de devoluciones y garantías)")
check(r.categoria == Categoria.FAQ_ESTATICA and r.metodo == "rag" and r.fuente,
      "compuerta SI + respuesta fundada -> faq_estatica con fuente citada")

r = _run(0.90, "SI", "No hay información en el contexto proporcionado sobre eso.")
check(r.categoria == Categoria.CON_HUMANO and r.metodo == "rag_sin_fundamento",
      "1ª frase 'no hay información en el contexto' -> con_humano (regex de respaldo)")

r = _run(0.90, "SI",
         "No, el Producto Alfa no viene con garantía extendida; la garantía cubre "
         "defectos de fábrica 12 meses. No se menciona en el contexto una garantía extendida. "
         "(Fuente: Preguntas frecuentes)")
check(r.categoria == Categoria.FAQ_ESTATICA and r.metodo == "rag",
      "respuesta válida con aclaración 'no se menciona' al final -> NO se deflecta")

print()
if _fallos:
    print(f"❌ {len(_fallos)} fallo(s)")
    sys.exit(1)
print("✅ Todo verde")
