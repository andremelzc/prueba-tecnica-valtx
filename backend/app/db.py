"""Registro de cada consulta en SQLite.

Una fila por llamada a `POST /consulta`, sin importar la categoría ni si fue un
duplicado. La tabla es el log/fuente de verdad (el cache de dedup es solo una
optimización en memoria).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from .config import SQLITE_PATH
from .schemas import ConsultaRequest, ConsultaResponse

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consultas (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT    NOT NULL,
    texto                TEXT    NOT NULL,
    canal                TEXT    NOT NULL,
    categoria            TEXT    NOT NULL,
    respuesta            TEXT    NOT NULL,
    fuente               TEXT,
    confianza            REAL    NOT NULL,
    metodo_clasificacion TEXT    NOT NULL,
    es_duplicado         INTEGER NOT NULL,
    resumen              TEXT
);
"""

# SQLite admite una sola escritura a la vez; serializamos desde el proceso.
_lock = threading.Lock()


def _conectar() -> sqlite3.Connection:
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(SQLITE_PATH, timeout=5.0)


def init_db() -> None:
    with _lock:
        conn = _conectar()
        try:
            conn.execute(_SCHEMA)
            conn.commit()
        finally:
            conn.close()


def registrar_consulta(req: ConsultaRequest, resp: ConsultaResponse) -> int:
    """Inserta una fila y devuelve su id."""
    fila = (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        req.texto,
        req.canal,
        resp.categoria.value,
        resp.respuesta,
        resp.fuente,
        float(resp.confianza),
        resp.metodo_clasificacion,
        1 if resp.es_duplicado else 0,
        resp.resumen,
    )
    with _lock:
        conn = _conectar()
        try:
            cur = conn.execute(
                "INSERT INTO consultas "
                "(timestamp, texto, canal, categoria, respuesta, fuente, confianza, "
                " metodo_clasificacion, es_duplicado, resumen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                fila,
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def contar() -> int:
    conn = _conectar()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM consultas").fetchone()[0])
    finally:
        conn.close()
