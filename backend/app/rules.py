"""Reglas por keyword para la clasificación rápida de intención.

Cada categoría tiene una lista de patrones (regex, sobre el texto normalizado y
*sin acentos*). El clasificador suma el peso de los patrones que hacen match y se
queda con la categoría de mayor puntaje; los empates se rompen con
`PRIORIDAD_CATEGORIAS`.

La idea es cubrir los casos obvios (que en el CSV de ejemplo son la mayoría) y
dejar SIN match lo genuinamente ambiguo ("hola, tengo una duda", "¿eso se
puede?", "quiero información"...) para que el fallback al LLM se encargue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Categoria


@dataclass(frozen=True)
class Regla:
    patron: re.Pattern
    peso: float = 1.0


def _r(expr: str, peso: float = 1.0) -> Regla:
    return Regla(re.compile(expr), peso)


# NOTA: todos los patrones asumen entrada ya pasada por `normalizar_match`
# (minúsculas, sin acentos, espacios colapsados).

REGLAS: dict[Categoria, list[Regla]] = {
    # ------------------------------------------------------------------
    # con_humano: quejas, negociaciones, excepciones, casos especiales.
    # Peso alto: si aparece uno de estos, casi siempre hay que escalar.
    # ------------------------------------------------------------------
    Categoria.CON_HUMANO: [
        _r(r"\bquej[ao]s?\b", 3.0),
        _r(r"\breclam(o|ar|acion|os)?\b", 3.0),
        _r(r"\bnegoci(ar|acion|ando)\b", 3.0),
        _r(r"\bexcepcion(es)?\b", 3.0),
        _r(r"\bcaso\s+(es\s+)?especial\b", 3.0),
        _r(r"\brevis(arlo|en|ar)\s+.*manual", 1.5),
        _r(r"\bmanualmente\b", 1.0),
        _r(r"\breembolso\b", 2.0),
        _r(r"\bdanad[oa]s?\b", 2.0),
        _r(r"\bllego\s+danad", 1.5),
        _r(r"\bya\s+paso\s+el\s+plazo\b", 3.0),
        _r(r"\bfuera\s+de\s+plazo\b", 3.0),
        _r(r"\bnuevo\s+proveedor\b", 2.0),
        _r(r"\bfuera\s+del\s+proceso\b", 2.0),
        _r(r"\bcompra\s+urgente\b", 1.5),
        _r(r"\bcotizacion\s+a\s+(la\s+)?medida\b", 2.0),
        _r(r"\bcotizacion\s+a\s+medida\b", 2.0),
        _r(r"\bproyecto\s+grande\b", 1.0),
        _r(r"\bhablar\s+con\s+(alguien|una\s+persona|un\s+humano|un\s+asesor)\b", 2.0),
        _r(r"\bmayor\s+al\s+de\s+la\s+tabla\b", 2.0),
        _r(r"\bcomplicado\s+de\s+explicar\b", 1.5),
        _r(r"\bno\s+es\s+lo\s+que\s+esperaba\b", 1.5),
        _r(r"\baunque\s+(ya\s+)?us[eo]\s+el\s+producto\b", 1.5),
    ],
    # ------------------------------------------------------------------
    # dato_dinamico: precio, stock, promociones, tipo de cambio.
    # NUNCA se responden con el LLM.
    # ------------------------------------------------------------------
    Categoria.DATO_DINAMICO: [
        _r(r"\bprecios?\b", 2.0),
        _r(r"\bcuesta\b", 2.0),
        _r(r"\bcuestan\b", 2.0),
        _r(r"\bcuanto\s+(cuesta|vale|sale|cuestan)\b", 2.0),
        _r(r"\bvalor\s+actual\b", 1.5),
        _r(r"\bstock\b", 2.0),
        _r(r"\bhay\s+(disponible|disponibilidad)\b", 1.5),
        _r(r"\bdisponible\s+(hoy|esta\s+semana|ahora)\b", 1.5),
        _r(r"\bpromo(cion|ciones)?\b", 2.0),
        _r(r"\bvigente\b", 1.5),
        _r(r"\bsigue\s+(vigente|igual)\b", 1.5),
        _r(r"\btipo\s+de\s+cambio\b", 2.0),
        _r(r"\bproximo\s+lote\b", 1.5),
        _r(r"\bcuando\s+llega\s+(el\s+)?(proximo\s+)?lote\b", 1.5),
        _r(r"\blista\s+de\s+(enero|precios)\b", 1.5),
        _r(r"\bpara\s+cotizar\s+hoy\b", 1.5),
        _r(r"\bdescuento\s+de\s+fin\s+de\s+ano\b", 1.5),
        _r(r"\bresponsable\s+de\s+compras\b", 2.0),
        _r(r"\bquien\s+es\s+el\s+responsable\b", 1.5),
    ],
    # ------------------------------------------------------------------
    # otra_area: fuera del alcance comercial (RRHH, TI, servicios internos).
    # ------------------------------------------------------------------
    Categoria.OTRA_AREA: [
        _r(r"\bcontrasena\b", 3.0),
        _r(r"\bpassword\b", 3.0),
        _r(r"\breset(eo|ear|eo\s+mi)\b", 1.5),
        _r(r"\bsueldos?\b", 3.0),
        _r(r"\bsalario\b", 3.0),
        _r(r"\bvacaciones\b", 3.0),
        _r(r"\brecursos\s+humanos\b", 3.0),
        _r(r"\brr\.?hh\b", 2.0),
        _r(r"\blaptop\b", 2.0),
        _r(r"\bcomputadora\b", 1.5),
        _r(r"\bse\s+me\s+malogr[oa]\b", 1.5),
        _r(r"\bmalogr[oa]\b", 1.0),
        _r(r"\bcomedor\b", 2.0),
        _r(r"\bacceso\s+al\s+sistema\b", 1.5),
        _r(r"\bsistema\s+de\s+facturacion\b", 1.5),
        _r(r"\bsoporte\s+ti\b", 2.0),
        _r(r"\bmesa\s+de\s+ayuda\b", 1.5),
        _r(r"\boficina\s+de\s+recursos\s+humanos\b", 2.0),
    ],
    # ------------------------------------------------------------------
    # faq_estatica: respondible con el documento de referencia.
    # ------------------------------------------------------------------
    Categoria.FAQ_ESTATICA: [
        _r(r"\bcomo\s+(solicito|solicitar|pido|pedir|hago\s+para\s+solicitar)\b", 2.0),
        _r(r"\bpasos\s+para\s+(pedir|solicitar)\b", 2.0),
        _r(r"\bpasos\s+sigo\s+para\s+solicitar\b", 2.0),
        _r(r"\bpara\s+solicitar\s+(el|un|mi)\b", 1.5),
        _r(r"\bsolicitar\b", 1.0),
        _r(r"\bformulario\s+(de\s+solicitud|f-?01)\b", 2.0),
        _r(r"\bformulario\b", 1.0),
        _r(r"\bsolicitud(es)?\b", 1.0),
        _r(r"\bplazo\b", 1.5),
        _r(r"\bdevoluc(ion|iones)\b", 1.5),
        _r(r"\bdevolv(er|erlo|erla)\b", 1.5),
        _r(r"\bhacer\s+una\s+devolucion\b", 1.5),
        _r(r"\bgarantia\b", 1.5),
        _r(r"\bdefectos?\s+de\s+fabrica\b", 1.5),
        _r(r"\bpolitica(s)?\b", 1.5),
        _r(r"\bcatalogo\b", 1.5),
        _r(r"\bcod-?(alf|bet|gam)\b", 2.0),
        _r(r"\bcancelar\s+(una|mi)\s+solicitud\b", 2.0),
        _r(r"\bmodificar\s+(mi|una|la)\s+solicitud\b", 2.0),
        _r(r"\bmodificar\s+mi\s+solicitud\b", 2.0),
        _r(r"\bsla\b", 2.0),
        _r(r"\btiempo\s+de\s+atencion\b", 1.5),
        _r(r"\bempaque\s+original\b", 1.5),
        _r(r"\bnumero\s+de\s+solicitud\b", 1.5),
        _r(r"\bdescuento\s+(por\s+volumen|por\s+cantidad)\b", 1.5),
        _r(r"\bdescuento\b.*\bunidades\b", 1.5),
        _r(r"\bunidades\b.*\bdescuento\b", 1.5),
        _r(r"\bpedidos?\s+de\s+\d+\s+unidades\b", 1.5),
        _r(r"\bvarios\s+productos\s+en\s+una\s+(sola\s+)?solicitud\b", 1.5),
        _r(r"\bcuanto\s+dura\s+la\s+garantia\b", 2.0),
        _r(r"\bcuantos?\s+dias\b.*\b(devol|entrega|garantia)\b", 1.5),
        _r(r"\bque\s+informacion\b.*\bsolicitud\b", 1.5),
        _r(r"\bque\s+productos\s+incluye\s+el\s+catalogo\b", 2.0),
        _r(r"\bque\s+necesito\s+para\s+(hacer\s+una\s+)?(devolucion|devolver)\b", 1.5),
        # Preguntas de INFORMACIÓN sobre producto/servicio/condiciones. Aunque el
        # dato no esté en el documento, entran por el RAG: el umbral de confianza
        # (Paso 3) las deriva a con_humano "por el camino correcto" (similitud
        # real), no porque el LLM adivine que son quejas.
        _r(r"\bpagar\s+en\s+cuotas\b", 1.3),
        _r(r"\ben\s+cuotas\b", 1.3),
        _r(r"\b(formas?|medios?|metodos?|opciones)\s+de\s+pago\b", 1.3),
        _r(r"\bfinanciamiento\b", 1.3),
        _r(r"\bsoporte\s+tecnico\b", 1.3),
        _r(r"\bpost-?venta\b", 1.3),
        _r(r"\bposventa\b", 1.3),
        _r(r"\bcertificacion(es)?\b", 1.3),
        _r(r"\benvi(o|os|an|ar)\b", 1.3),
        _r(r"\ba\s+provincia(s)?\b", 1.3),
        _r(r"\bgarantia\s+extendida\b", 1.3),
    ],
}
