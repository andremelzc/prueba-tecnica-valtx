"""Descarga el modelo GGUF del LLM local a backend/models/ (una sola vez).

    python -m scripts.descargar_modelo

Repo por defecto: microsoft/Phi-3-mini-4k-instruct-gguf
Archivo:          Phi-3-mini-4k-instruct-q4.gguf  (~2.4 GB, cuantización Q4_K_M)

Se puede sobrescribir con env vars: LLM_HF_REPO, LLM_HF_FILE, LLM_MODEL_PATH.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import LLM_MODEL_PATH, MODELS_DIR  # noqa: E402

HF_REPO = os.getenv("LLM_HF_REPO", "microsoft/Phi-3-mini-4k-instruct-gguf")
HF_FILE = os.getenv("LLM_HF_FILE", "Phi-3-mini-4k-instruct-q4.gguf")


def main() -> None:
    destino = Path(LLM_MODEL_PATH)
    if destino.exists():
        print(f"El modelo ya está en {destino} ({destino.stat().st_size / 1e9:.2f} GB). Nada que hacer.")
        return

    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {HF_REPO}/{HF_FILE} ...")
    ruta_cache = hf_hub_download(repo_id=HF_REPO, filename=HF_FILE)

    # hf_hub_download deja el archivo en la caché de HF; lo copiamos a models/
    # con el nombre que espera la app para no depender de la caché.
    shutil.copyfile(ruta_cache, destino)
    print(f"Listo: {destino} ({destino.stat().st_size / 1e9:.2f} GB)")


if __name__ == "__main__":
    main()
