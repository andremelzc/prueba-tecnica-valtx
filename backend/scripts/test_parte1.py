"""Pruebas rápidas de la Parte 1 (normalización + reglas), sin dependencias.

    python -m scripts.test_parte1
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import clasificar_por_reglas  # noqa: E402
from app.config import AMBIGUO, Categoria  # noqa: E402
from app.normalization import (  # noqa: E402
    RecentQueryCache,
    clave_dedup,
    normalizar,
    normalizar_match,
)

_fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    estado = "ok  " if cond else "FALLA"
    print(f"[{estado}] {msg}")
    if not cond:
        _fallos.append(msg)


# --- normalización --------------------------------------------------------

check(normalizar("  Hola,   \n TENGO una DUDA???  ") == "hola, tengo una duda?", "normaliza espacios/mayúsculas/puntuación repetida")
check(normalizar_match("¿Cómo está la garantía?") == "¿como esta la garantia?", "normalizar_match quita acentos")
check(clave_dedup("¿Cómo solicito un producto del catálogo?") == "como solicito un producto del catalogo", "clave_dedup quita signos y acentos")

# --- casi-duplicados -----------------------------------------------------

cache = RecentQueryCache()
q1 = normalizar("¿Cómo solicito un producto del catálogo?")
check(cache.buscar_duplicado(q1) is None, "primera consulta no es duplicado")
cache.registrar(q1, payload={"respuesta": "abre el formulario F-01", "confianza": 0.9})

dup = cache.buscar_duplicado(normalizar("como solicito un producto del catalogo"))
check(dup is not None and dup.score >= 90, "variante sin acentos/signos se detecta como duplicado")
check(dup is not None and dup.payload["respuesta"] == "abre el formulario F-01", "el duplicado devuelve la respuesta cacheada")

no_dup = cache.buscar_duplicado(normalizar("¿Cuánto dura la garantía?"))
check(no_dup is None, "consulta distinta no se marca como duplicado")

# --- clasificador por reglas -------------------------------------------

CASOS = [
    ("¿Cómo solicito un producto del catálogo?", Categoria.FAQ_ESTATICA),
    ("¿Cuál es el plazo para devolver un producto?", Categoria.FAQ_ESTATICA),
    ("¿Cómo funciona la garantía de los productos?", Categoria.FAQ_ESTATICA),
    ("¿Cuál es el precio actual del Producto Alfa?", Categoria.DATO_DINAMICO),
    ("¿Hay stock disponible del Producto Beta hoy?", Categoria.DATO_DINAMICO),
    ("¿Qué promoción está vigente este mes?", Categoria.DATO_DINAMICO),
    ("¿Cuánto cuesta?", Categoria.DATO_DINAMICO),
    ("¿Cómo reseteo mi contraseña del correo?", Categoria.OTRA_AREA),
    ("¿Cuándo pagan los sueldos este mes?", Categoria.OTRA_AREA),
    ("¿Cómo solicito mis vacaciones?", Categoria.OTRA_AREA),
    ("Tengo una queja sobre la atención que recibí, ¿con quién hablo?", Categoria.CON_HUMANO),
    ("Necesito un descuento mayor al de la tabla, ¿pueden hacer una excepción?", Categoria.CON_HUMANO),
    ("Un producto llegó dañado y ya pasó el plazo de devolución, ¿qué hacen?", Categoria.CON_HUMANO),
    ("Necesito hablar con alguien, es complicado de explicar por chat.", Categoria.CON_HUMANO),
    # ambiguas -> deben ir al LLM
    ("Hola, tengo una duda.", AMBIGUO),
    ("¿Eso se puede?", AMBIGUO),
    ("Quiero información.", AMBIGUO),
]

for texto, esperado in CASOS:
    res = clasificar_por_reglas(normalizar(texto))
    ok = res.categoria == esperado
    etiqueta_esp = esperado if esperado == AMBIGUO else esperado.value
    etiqueta_obt = res.categoria if res.categoria == AMBIGUO else res.categoria.value
    check(ok, f"{texto!r} -> {etiqueta_obt} (esperado {etiqueta_esp})")

print()
if _fallos:
    print(f"❌ {len(_fallos)} fallo(s)")
    sys.exit(1)
print("✅ Todo verde")
