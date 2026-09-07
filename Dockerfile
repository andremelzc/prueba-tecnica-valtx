# Imagen única: buildea el frontend, lo mete dentro del backend y FastAPI lo sirve.
# Pensada para Hugging Face Spaces (SDK: docker, app_port: 7860).

# ---------- 1. Frontend (Vite build estático) ----------
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Sin VITE_API_URL: el build de prod usa rutas relativas (mismo origen que el backend).
RUN rm -f .env .env.local && npm run build


# ---------- 2. Backend (FastAPI + LLM local + Qdrant embebido) ----------
FROM python:3.13-slim AS backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    HOME=/app \
    LLM_N_THREADS=2

WORKDIR /app

# Toolchain para compilar llama-cpp-python (si no hay wheel) + utilidades.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git curl \
    && rm -rf /var/lib/apt/lists/*

# torch en versión CPU (evita arrastrar ~3 GB de librerías CUDA).
RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Se bakean los modelos en la imagen para que el contenedor arranque sin descargas:
#  - GGUF del LLM (~2.4 GB)
RUN python -m scripts.descargar_modelo
#  - embeddings e5-small (~120 MB) a la caché de HF
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

# Frontend build servido por FastAPI en el mismo origen.
COPY --from=frontend /fe/dist ./static

# HF Spaces espera un usuario con UID 1000 y $HOME escribible.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
