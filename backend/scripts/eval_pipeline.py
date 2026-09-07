"""Corre las 80 consultas del CSV por el pipeline COMPLETO (reglas + LLM).

Muestra: tabla por consulta, conteo por categoría final, conteo por método de
clasificación, y el detalle de los casos que resolvió el LLM (con su razón).

    python -m scripts.eval_pipeline
    SKIP_LLM=1 python -m scripts.eval_pipeline   # sin LLM: los AMBIGUO quedan sin resolver
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

from app.classifier import clasificar_por_reglas  # noqa: E402
from app.config import AMBIGUO  # noqa: E402
from app.llm import clasificar_intencion_llm  # noqa: E402
from app.normalization import RecentQueryCache, normalizar  # noqa: E402
from app.pipeline import procesar_consulta  # noqa: E402

CSV_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "consultas_ejemplo.csv"


def main(csv_path: Path) -> None:
    usar_llm = os.getenv("SKIP_LLM") != "1"
    llm_fn = clasificar_intencion_llm if usar_llm else None
    if usar_llm:
        from app.llm import cargar_llm

        print("Cargando LLM ...", flush=True)
        t0 = time.time()
        cargar_llm()
        print(f"LLM cargado en {time.time() - t0:.1f}s\n", flush=True)

    cache = RecentQueryCache()
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))

    conteo_cat: dict[str, int] = {}
    conteo_metodo: dict[str, int] = {}
    resueltos_llm = []

    print(f"{'id':<6}{'categoría final':<16}{'método':<20}{'conf':<7}consulta")
    print("-" * 110)
    t0 = time.time()
    for row in filas:
        texto = row["consulta"]
        regla = clasificar_por_reglas(normalizar(texto))

        resp = procesar_consulta(texto, row["canal"], cache=cache, llm_fn=llm_fn)
        cat = resp.categoria.value
        conteo_cat[cat] = conteo_cat.get(cat, 0) + 1
        conteo_metodo[resp.metodo_clasificacion] = conteo_metodo.get(resp.metodo_clasificacion, 0) + 1

        if regla.categoria == AMBIGUO and resp.metodo_clasificacion != "duplicado":
            resueltos_llm.append((row["id"], texto, cat, resp.metodo_clasificacion, resp.razon))

        print(f"{row['id']:<6}{cat:<16}{resp.metodo_clasificacion:<20}{resp.confianza:<7}{texto}")

    dt = time.time() - t0
    print(f"\n({len(filas)} consultas en {dt:.1f}s"
          + (f", ~{dt / max(len(resueltos_llm), 1):.1f}s por llamada al LLM)" if usar_llm else ")"))

    print("\n== Categoría final (pipeline completo) ==")
    for cat, n in sorted(conteo_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:<16} {n}")

    print("\n== Método de clasificación ==")
    for m, n in sorted(conteo_metodo.items(), key=lambda kv: -kv[1]):
        print(f"  {m:<22} {n}")

    print(f"\n== Casos que resolvió el LLM ({len(resueltos_llm)}) ==")
    for cid, texto, cat, metodo, razon in resueltos_llm:
        print(f"  {cid}  {cat:<14} [{metodo}]  {texto}")
        print(f"        razón: {razon}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_DEFAULT
    main(path)
