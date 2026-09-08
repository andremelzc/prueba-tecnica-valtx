# Deploy — opciones y análisis

> **Para la prueba técnica el deploy no es un requisito.** Lo importante es que se
> pueda correr desde cero en la máquina del evaluador (ver [`README.md`](README.md)).
> Este documento resume las opciones de deploy evaluadas y por qué, dado el
> requisito de **modelo self-hosted (on-premise) + costo cero**, la única forma
> real de exponerlo en una URL pública gratis es *tu propia máquina + un túnel*.

---

## 1. En qué se gastan los recursos

El cuello de botella es **el modelo y su inferencia**, no la librería que lo sirve
(`llama-cpp-python`, Ollama y vLLM corren el mismo modelo con el mismo costo de
RAM/CPU; vLLM incluso es más pesado porque quiere pesos FP16).

### RAM (después de cargar, en reposo)

| Componente | RAM |
|---|---|
| Pesos de Phi-3-mini Q4 (mmap) | ~2.4 GB |
| KV cache + buffers de `llama.cpp` (`n_ctx=4096`) | ~0.6–1 GB |
| PyTorch (lo importa `sentence-transformers` para los embeddings) | ~1 GB |
| Modelo de embeddings `multilingual-e5-small` | ~0.5 GB |
| Python + FastAPI + libs (`transformers`, `qdrant-client`, …) | ~0.4 GB |
| Qdrant embebido (21 chunks) | ~0.1 GB |
| **Total** | **~5 GB en reposo · ~7–8 GB de pico durante una consulta** |

### CPU

- En reposo: 0.
- Durante una llamada al LLM: **todos los threads al 100 %** durante toda la
  generación. Es la parte cara — generar tokens es matemática de matrices.
- Embedding de la consulta (e5): pico de ~1 s.
- Reglas, deduplicación, SQLite: despreciable.

### Disco

| Qué | Tamaño |
|---|---|
| GGUF del modelo | 2.4 GB |
| Dependencias de Python (torch es el grande: ~2–3 GB en Linux) | ~3–5 GB |
| `e5-small` en la caché de Hugging Face | ~0.5 GB |
| Qdrant local + SQLite | pocos MB |
| **Total** | **~8–10 GB** |

### Tiempos

| Momento | Duración |
|---|---|
| Arranque en frío (importar torch + cargar e5 + **cargar el GGUF de 2.4 GB** + indexar Qdrant) | **~25–30 s** |
| Request resuelto por reglas (`dato_dinamico`, `otra_area`, la mayoría) | < 50 ms |
| Clasificación por LLM (consulta ambigua) | 1 llamada · ~8–15 s |
| `con_humano` (regla + resumen para el revisor) | 1 llamada · ~5–10 s |
| **`faq_estatica` vía RAG** (compuerta + generación) | **2 llamadas · ~30–45 s** |
| Duplicado (cache hit) | < 10 ms |

> Todo esto es en **CPU**. Con GPU la generación es 10–50× más rápida.

---

## 2. Por qué los PaaS gratis no alcanzan

El free tier de cualquier PaaS está pensado para una API liviana, no para
hostear un LLM de ~4B parámetros.

| Plataforma | Free tier | ¿Entra el backend tal cual? |
|---|---|---|
| **Render** Free | 512 MB RAM · 0.1 vCPU | ❌ OOM al cargar el modelo. Y 0.1 vCPU tardaría *minutos* por respuesta / timeout |
| Render Standard $25/mo | 2 GB | ❌ OOM |
| Render Pro Plus $175/mo | 8 GB · 4 vCPU | ✅ pero $175/mo es absurdo para esto |
| **Hugging Face Spaces** | SDK Docker y Gradio → **de pago**; solo *Static* es free | ❌ (Static sirve solo para el frontend, no corre backend) |
| **Fly.io / Koyeb / Railway** free | 256–512 MB | ❌ |
| **AWS / GCP / Azure** "always free" | 1 GB (t2.micro, e2-micro, B1S) | ❌ |
| **Oracle Cloud** Always Free (ARM A1) | 4 vCPU · **24 GB RAM** · gratis para siempre | ✅ en teoría, pero **"out of capacity" casi permanente** en las regiones útiles; aprobación de cuenta lenta; reclaman instancias idle. Poco confiable con una fecha de entrega |

**Render en particular** falla por dos motivos, no uno: RAM (necesita 8 GB = plan
de $175) **y** CPU (los planes baratos dan 0.1–0.5 vCPU, imposible para un 3.8B).

Render *sí* funcionaría si se saca el modelo local y se usa una API (Claude
Haiku / Gemini Flash) → el backend baja a ~1–2 GB y entra en Standard $25. Pero
eso **rompe el requisito de "modelo self-hosted / on-premise"**.

---

## 3. Opción recomendada: tu máquina + Cloudflare Tunnel

Es lo más literalmente *on-premise* (corre en tu hardware), gratis, sin tarjeta,
y funciona en ~10 minutos.

```bash
# 1. instalar cloudflared
winget install --id Cloudflare.cloudflared          # Windows
#   o: brew install cloudflared                     # macOS
#   o: https://github.com/cloudflare/cloudflared/releases

# 2. levantar el backend local (como siempre)
cd backend && uvicorn main:app                       # :8000

# 3. túnel público (en otra terminal)
cloudflared tunnel --url http://localhost:8000
```

Devuelve una URL `https://<random>.trycloudflare.com`. **Sin cuenta, sin config.**
Vive mientras el proceso `cloudflared` esté corriendo.

- El frontend se buildea y se deja en **Cloudflare Pages / Netlify / HF Static
  Space** (gratis), con `VITE_API_URL` apuntando a esa URL.
- **Contras:** la máquina tiene que estar prendida y con los dos procesos
  corriendo. La URL cambia al reiniciar el túnel (para URL fija gratis hace falta
  un dominio en Cloudflare). Alternativa casi igual: **ngrok free** da un
  subdominio `*.ngrok-free.app` fijo por cuenta (registro sin tarjeta).

Para una demo en vivo o una ventana de revisión de pocos días: dejás la laptop
enchufada, suspensión desactivada, y mandás la URL. Conviene además grabar un
**video corto** mostrándolo andando, por si miran el link con el túnel caído.

---

## 4. Alternativa: Google Cloud Run (free tier)

Gratis bajo los límites del free tier, pero **requiere una tarjeta** en la cuenta
(no cobra si no te pasás).

```bash
gcloud run deploy asistente --source . \
  --memory 8Gi --cpu 4 --port 7860 \
  --min-instances 0 --max-instances 1 --concurrency 4 --timeout 300
```

- **Debe escalar a cero** (`--min-instances 0`) para no gastar el free tier
  (360.000 GB-segundo/mes → con 8 GB son ~12 h de contenedor activo).
- Con `min-instances=0`, el primer request tras inactividad paga el **arranque en
  frío** (~40 s con Phi-3; ~10 s con un modelo chico).
- Usa el mismo `Dockerfile` de la raíz.

---

## 5. Si hiciera falta que entre en un free tier de PaaS

Se puede achicar el backend de ~7 GB a ~2 GB cambiando las dos piezas pesadas.
**No implementado** (el enunciado no lo pide), pero anotado:

| Cambio | Efecto |
|---|---|
| `Phi-3-mini` (2.4 GB) → **`Qwen2.5-0.5B-Instruct` Q4** (~0.4 GB) | La clasificación (tarea acotada, JSON forzado por gramática) sigue andando bien; la generación de FAQ pierde calidad |
| `sentence-transformers` (+torch ~1.5 GB) → **`fastembed`** (ONNX, ~0.2 GB) | Mismo modelo e5, sin PyTorch |
| `n_ctx` 4096 → 2048 | Menos KV cache |
| **Total** | **~1.5–2.5 GB** → entra en Cloud Run free / Render Standard / un VPS de 2 GB |

El pipeline (`app/pipeline.py`) no cambia — es agnóstico al modelo. Solo cambian
`app/llm.py`, `app/rag.py` y `app/config.py`.

---

## 6. Docker (para correr en la máquina de ellos)

El [`Dockerfile`](Dockerfile) de la raíz es multi-stage: buildea el frontend, lo
mete dentro del backend y FastAPI lo sirve en el puerto 7860 — **un contenedor,
una URL**. El GGUF y los embeddings se bakean en la imagen (arranca sin
descargas). Con [`docker-compose.yml`](docker-compose.yml):

```bash
docker compose up --build      # primera vez ~15–20 min (compila llama-cpp, baja el modelo)
# luego: http://localhost:8000
```

Esto sirve tanto para probarlo local como para deployarlo en cualquier VM con
Docker (Oracle, un VPS, etc.).
