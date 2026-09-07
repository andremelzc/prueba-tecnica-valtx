"""Normalización de texto y detección de casi-duplicados.

- `normalizar`      -> versión limpia y legible (para guardar / mostrar / embeddings).
- `normalizar_match` -> además sin acentos, pensada para el matching por keyword.
- `RecentQueryCache` -> ventana en memoria de consultas recientes; usa rapidfuzz
  para detectar si una consulta nueva es prácticamente la misma que otra reciente
  y, en ese caso, devolver la respuesta ya calculada sin recomputar.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from rapidfuzz import fuzz

from .config import DEDUP_MAX_ITEMS, DEDUP_THRESHOLD, DEDUP_TTL_SECONDS

_WS_RE = re.compile(r"\s+")
_REPEAT_PUNCT_RE = re.compile(r"([?!.,;:])\1+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9ñ ]+")


def quitar_acentos(texto: str) -> str:
    """Elimina tildes y diacríticos (á -> a, ñ -> n)."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Limpieza básica: minúsculas, espacios y puntuación repetida colapsados.

    Mantiene acentos y signos: sirve tanto para persistir la consulta como para
    generar embeddings con el modelo e5 (que es sensible a la ortografía).
    """
    texto = texto.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texto = texto.strip().lower()
    texto = _REPEAT_PUNCT_RE.sub(r"\1", texto)  # "???" -> "?", "!!!" -> "!"
    texto = _WS_RE.sub(" ", texto)
    return texto.strip()


def normalizar_match(texto: str) -> str:
    """Igual que `normalizar` pero sin acentos, para comparar keywords."""
    return quitar_acentos(normalizar(texto))


def clave_dedup(texto: str) -> str:
    """Clave canónica para comparar casi-duplicados.

    Sin acentos y sin puntuación: así "¿Cómo solicito...?" y "como solicito..."
    colapsan a la misma cadena y rapidfuzz no se distrae con signos.
    """
    base = quitar_acentos(normalizar(texto))
    base = _NON_ALNUM_RE.sub(" ", base)
    return _WS_RE.sub(" ", base).strip()


@dataclass
class _RecentQuery:
    texto_norm: str
    clave: str
    ts: float
    payload: Any = None  # respuesta ya calculada para esta consulta


@dataclass
class DuplicadoInfo:
    texto_previo: str
    score: float
    payload: Any = None  # respuesta cacheada del duplicado, si la hay


class RecentQueryCache:
    """Ventana en memoria de las últimas consultas normalizadas + su respuesta.

    Single-turn y sin user/session id: la misma pregunta textual siempre debe
    dar la misma respuesta determinística, así que ante un casi-duplicado se
    devuelve la respuesta cacheada tal cual, sin volver a clasificar ni llamar
    al LLM (que es justo donde más cuesta recomputar).

    Es una optimización, no la fuente de verdad: esa es el log en SQLite. Si el
    proceso reinicia y se pierde el cache, el peor caso es reprocesar un
    duplicado una vez más.
    """

    def __init__(
        self,
        maxlen: int = DEDUP_MAX_ITEMS,
        ttl_seconds: int = DEDUP_TTL_SECONDS,
        threshold: float = DEDUP_THRESHOLD,
    ) -> None:
        self._items: "deque[_RecentQuery]" = deque(maxlen=maxlen)
        self.ttl_seconds = ttl_seconds
        self.threshold = threshold

    def _prune(self, now: float) -> None:
        while self._items and (now - self._items[0].ts) > self.ttl_seconds:
            self._items.popleft()

    def buscar_duplicado(self, texto_norm: str) -> Optional[DuplicadoInfo]:
        """Devuelve el duplicado más parecido dentro de la ventana, o None."""
        now = time.time()
        self._prune(now)
        clave = clave_dedup(texto_norm)
        mejor: Optional[_RecentQuery] = None
        mejor_score = 0.0
        for item in self._items:
            # token_sort_ratio sobre la clave canónica (sin signos ni acentos):
            # robusto al orden de palabras y a variantes ortográficas menores.
            score = fuzz.token_sort_ratio(clave, item.clave)
            if score > mejor_score:
                mejor_score, mejor = score, item
        if mejor is not None and mejor_score >= self.threshold:
            return DuplicadoInfo(
                texto_previo=mejor.texto_norm,
                score=mejor_score,
                payload=mejor.payload,
            )
        return None

    def registrar(self, texto_norm: str, payload: Any = None) -> None:
        self._items.append(
            _RecentQuery(
                texto_norm=texto_norm,
                clave=clave_dedup(texto_norm),
                ts=time.time(),
                payload=payload,
            )
        )

    def clear(self) -> None:
        self._items.clear()
