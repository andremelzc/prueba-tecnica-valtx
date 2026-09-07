"""Pasa el CSV de consultas de ejemplo por normalización + reglas y muestra el
resultado en una tabla. Sirve para ver rápidamente qué resuelven las reglas y qué
queda AMBIGUO (pendiente del LLM).

Uso:
    python -m scripts.eval_clasificador
    python -m scripts.eval_clasificador data/consultas_ejemplo.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:  # consola de Windows: forzar UTF-8 para no ver mojibake
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

from app.classifier import clasificar_por_reglas  # noqa: E402
from app.config import AMBIGUO  # noqa: E402
from app.normalization import RecentQueryCache, normalizar  # noqa: E402

CSV_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "consultas_ejemplo.csv"


def main(csv_path: Path) -> None:
    cache = RecentQueryCache()
    filas = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            filas.append(row)

    conteo: dict[str, int] = {}
    ambiguos = []
    duplicados = []

    print(f"{'id':<6}{'categoría (reglas)':<20}{'conf':<7}{'dup':<5}consulta")
    print("-" * 100)
    for row in filas:
        texto = row["consulta"]
        norm = normalizar(texto)

        dup = cache.buscar_duplicado(norm)
        cache.registrar(norm)

        res = clasificar_por_reglas(norm)
        cat = AMBIGUO if res.categoria == AMBIGUO else res.categoria.value
        cat_label = "AMBIGUO -> LLM" if cat == AMBIGUO else cat
        conteo[cat] = conteo.get(cat, 0) + 1

        marca_dup = f"{dup.score:.0f}" if dup else ""
        if dup:
            duplicados.append((row["id"], texto, dup.texto_previo, dup.score))
        if cat == AMBIGUO:
            ambiguos.append((row["id"], texto))

        print(f"{row['id']:<6}{cat_label:<20}{res.confianza:<7}{marca_dup:<5}{texto}")

    print("\n== Resumen ==")
    for cat, n in sorted(conteo.items(), key=lambda kv: -kv[1]):
        etiqueta = "AMBIGUO (-> LLM)" if cat == AMBIGUO else cat
        print(f"  {etiqueta:<22} {n}")

    print(f"\n== Ambiguas ({len(ambiguos)}) -> las resolverá el LLM ==")
    for cid, texto in ambiguos:
        print(f"  {cid}: {texto}")

    print(f"\n== Casi-duplicados detectados ({len(duplicados)}) ==")
    for cid, texto, previo, score in duplicados:
        print(f"  {cid} ({score:.0f}): {texto!r}  ~=  {previo!r}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_DEFAULT
    main(path)
