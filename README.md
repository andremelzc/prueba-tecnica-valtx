---
title: Asistente de Consultas Comerciales
emoji: 💬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Clasifica y responde consultas comerciales (reglas + LLM local + RAG)
---

# Asistente de consultas comerciales — prueba técnica

Backend (FastAPI) + frontend (React/Vite) para un asistente de consultas
comerciales **single-turn**. Todo self-hosted: el LLM corre local (Phi-3-mini
GGUF vía `llama-cpp-python`), sin llamadas a APIs externas.

## Flujo

```
{texto, canal}  →  normalizar  →  ¿casi-duplicado? (cache)
                       │
                       ▼
             clasificar en 4 categorías
             ├─ reglas por keyword (~84%)
             └─ fallback al LLM local (lo ambiguo)
                       │
                       ▼
   faq_estatica   → RAG (Qdrant + e5) → respuesta del LLM citando la fuente
   dato_dinamico  → mensaje fijo (nunca LLM)
   otra_area      → mensaje fijo
   con_humano     → mensaje fijo + resumen del LLM para el revisor
                       │
                       ▼
            registro en SQLite  →  { categoria, respuesta, fuente,
                                      confianza, metodo_clasificacion, es_duplicado }
```

Detalle de cada etapa en [`backend/README.md`](backend/README.md) y del frontend
en [`frontend/README.md`](frontend/README.md).

## Correr local

```bash
# backend (terminal 1)
cd backend
python -m venv venv && ./venv/Scripts/activate   # o source venv/bin/activate
pip install -r requirements.txt
python -m scripts.descargar_modelo               # baja el GGUF (~2.4 GB)
uvicorn main:app --reload                         # :8000

# frontend (terminal 2)
cd frontend
npm install
npm run dev                                       # :5173
```

## Deploy (Hugging Face Spaces, Docker, free tier)

El `Dockerfile` de la raíz buildea el frontend, lo mete dentro del backend y
FastAPI lo sirve — **un solo contenedor, una sola URL**. El modelo GGUF y los
embeddings se bakean en la imagen (arranca sin descargas).

```bash
# crear el Space en huggingface.co/new-space  (SDK: Docker)
git remote add space https://huggingface.co/spaces/<usuario>/<nombre>
git push space main
```

HF buildea en su infra (~15-20 min la primera vez). Requisitos que cubre el free
tier: 2 vCPU / 16 GB RAM.

## Tests

```bash
cd backend
python -m scripts.test_parte1     # normalización + reglas
python -m scripts.test_parte2     # fallback LLM (sin modelo)
python -m scripts.test_parte3     # indexing + umbral RAG (sin modelo)
python -m scripts.test_parte4     # endpoint + SQLite (sin modelo)
python -m scripts.eval_pipeline   # CSV completo (necesita el modelo)
```
