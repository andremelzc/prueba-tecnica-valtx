# Asistente de consultas comerciales

Prueba técnica. Backend (FastAPI) + frontend (React/Vite) para un asistente que
recibe una consulta comercial, la **clasifica en una de 4 categorías** y responde
según corresponda. **Single-turn** (cada consulta es independiente) y
**self-hosted**: el LLM corre local (Phi-3-mini GGUF vía `llama-cpp-python`), sin
llamadas a APIs externas.

```
{texto, canal}  →  normalizar  →  ¿casi-duplicado? (cache en memoria)
                       │
                       ▼
             clasificar en 4 categorías
             ├─ reglas por keyword           (~84 % de la muestra)
             └─ fallback al LLM local         (solo lo ambiguo)
                       │
                       ▼
   faq_estatica   → RAG (Qdrant + embeddings e5) → respuesta del LLM citando la fuente
                    (si no está fundado en el documento → deriva a con_humano, no inventa)
   dato_dinamico  → mensaje fijo (nunca pasa por el LLM)
   otra_area      → mensaje fijo
   con_humano     → mensaje fijo + resumen del LLM para el revisor
                       │
                       ▼
            registro en SQLite (siempre, también duplicados)
                       │
                       ▼
   { categoria, respuesta, fuente, confianza, metodo_clasificacion, es_duplicado }
```

- Detalle del pipeline, decisiones de diseño y resultados sobre la muestra:
  [`backend/README.md`](backend/README.md)
- Detalle del frontend: [`frontend/README.md`](frontend/README.md)
- Opciones de deploy y análisis de recursos: [`DEPLOY.md`](DEPLOY.md)

---

## Requisitos

| | |
|---|---|
| RAM | **~8 GB libres** (el modelo ocupa ~2.4 GB + torch + embeddings) |
| Disco | **~10 GB** (modelo 2.4 GB + dependencias) |
| CPU | 2–4 cores (cuantos más, menos lento; corre solo en CPU) |
| SO | Windows / macOS / Linux |

Y una de estas dos vías:

- **Docker** (Docker Desktop o Docker Engine), o
- **Python 3.13** + **Node 20+** para la vía manual.

---

## Correr desde cero

### Vía A — Docker (un comando)

```bash
git clone <repo> && cd prueba-tecnica-valtx
docker compose up --build
```

La primera vez tarda **~15–20 min**: compila `llama-cpp-python`, instala torch
(CPU), **descarga el modelo GGUF (~2.4 GB)** y buildea el frontend. Cuando
termine, todo queda en:

**http://localhost:8000** — frontend + API en el mismo origen.

> Arranques siguientes: ~30 s (carga el modelo a RAM).

### Vía B — Manual (dos terminales)

**Terminal 1 — backend**

```bash
cd backend
python -m venv venv
# Windows:  .\venv\Scripts\Activate.ps1      (si PowerShell lo bloquea:
#           Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt              # ~5–10 min (torch es grande)
python -m scripts.descargar_modelo           # baja el GGUF (~2.4 GB) a models/
uvicorn main:app --reload                     # http://localhost:8000
```

Esperá a que loguee `LLM cargado` y `Índice RAG: {...}` (~20–30 s la primera vez).

**Terminal 2 — frontend**

```bash
cd frontend
npm install
npm run dev                                   # http://localhost:5173
```

El `.env` ya apunta a `http://localhost:8000`. Abrí **http://localhost:5173**.

---

## Probar

### Desde la UI

- **Botones "Ejemplos"** (barra lateral): respuesta **instantánea**, una por
  categoría. Usan respuestas precomputadas (`frontend/src/ejemplos.data.json`),
  no llaman al backend.
- **Caja de texto**: consulta al backend real. Cada categoría tarda distinto:

  | Escribí… | Categoría | Tiempo aprox. (CPU) |
  |---|---|---|
  | `¿Cuál es el precio actual del Producto Alfa?` | `dato_dinamico` | instantáneo |
  | `¿Cuándo pagan los sueldos este mes?` | `otra_area` | instantáneo |
  | `Tengo una queja sobre la atención que recibí` | `con_humano` | ~5–10 s |
  | `Hola, tengo una duda` | `con_humano` (lo decide el LLM) | ~15–25 s |
  | `¿Cuál es el plazo para devolver un producto?` | `faq_estatica` (RAG) | ~30–45 s |
  | `¿Puedo pagar en cuotas?` | `con_humano` (RAG no lo encuentra en el doc) | ~30–45 s |

  Abrí **"Ver detalle"** en cada respuesta: fuente citada, score de confianza,
  método de clasificación (`regla` / `llm` / `rag_baja_confianza` / …), si fue
  duplicado, y el resumen para el revisor.

### Desde Swagger

**http://localhost:8000/docs** → `POST /consulta` con `{"texto": "...", "canal": "chat"}`.

### Tests

```bash
cd backend
python -m scripts.test_parte1     # normalización + reglas          (sin modelo)
python -m scripts.test_parte2     # fallback de clasificación al LLM (sin modelo)
python -m scripts.test_parte3     # indexing del .docx + umbral RAG  (sin modelo)
python -m scripts.test_parte4     # endpoint + SQLite + resumen      (sin modelo)
python -m scripts.eval_pipeline   # las 80 consultas del CSV por el pipeline completo (necesita el modelo)
```

---

## Estructura

```
├── backend/                 FastAPI + pipeline + LLM + RAG + SQLite
│   ├── app/                  config, schemas, normalization, rules, classifier,
│   │                         llm, indexing, rag, pipeline, db
│   ├── scripts/              descargar_modelo, eval_*, test_parte1..4
│   ├── data/                 documentos_referencia.docx, consultas_ejemplo.csv
│   └── README.md             ← detalle del pipeline y decisiones
├── frontend/                 React + Vite
│   ├── src/components/       Sidebar, ChatThread, Message, CategoryBadge, DetailPanel, Composer
│   └── README.md
├── Dockerfile                build multi-stage (frontend dentro del backend)
├── docker-compose.yml
├── DEPLOY.md                 opciones de deploy + análisis de recursos
└── README.md                (este archivo)
```

## Notas

- **Latencia:** todo corre en CPU. Las consultas `faq_estatica` hacen 2 llamadas
  al LLM (compuerta de relevancia + generación) → ~30–45 s. Es esperado; ver
  [`DEPLOY.md`](DEPLOY.md) para el desglose y qué lo aceleraría (GPU, modelo más
  chico, API).
- **SQLite** (`backend/data/consultas.db`) y el **cache de duplicados** (en
  memoria) se resetean al reiniciar / reconstruir. El log en SQLite persiste
  entre reinicios si no se borra el archivo.
- **Un solo proceso de backend a la vez**: `QdrantClient(path=...)` bloquea la
  carpeta del índice.
