# Deploy

El deploy no es un requisito de la prueba: lo importante es que corra desde cero
en la máquina del evaluador (ver [`README.md`](README.md)). Esta nota explica la
opción elegida para exponerlo en una URL y por qué.

## Por qué un túnel y no un PaaS

El requisito es **modelo self-hosted + costo cero**. El backend necesita ~8 GB de
RAM (pesos de Phi-3-mini ~2.4 GB + torch + embeddings e5 + buffers de llama.cpp)
y todos los cores de CPU durante cada inferencia. Ningún free tier de PaaS
(Render, Railway, Fly, Cloud Run sin tarjeta, Spaces) da esa RAM/CPU gratis, y
sacar el modelo local para usar una API rompería el requisito.

La forma viable sin costo ni tarjeta es correr el backend en la propia máquina y
publicarlo con un túnel.

## Cómo se expone

El frontend se compila **dentro** del backend, así que FastAPI sirve la app y la
API en el mismo origen: una sola URL para todo.

```bash
cd frontend && npm run build
# Windows PowerShell:
Copy-Item -Recurse -Force dist ../backend/static
# macOS/Linux:
# rm -rf ../backend/static && cp -r dist ../backend/static

cd ../backend && uvicorn main:app          # sirve API + frontend en :8000
```

- **Demo local / compartiendo pantalla:** abrir http://localhost:8000, sin túnel.
- **Link para que entren ellos:** ngrok con dominio estático gratis (fijo, sobrevive
  reinicios):

  ```bash
  ngrok http --url=<subdominio>.ngrok-free.app 8000
  ```

  Las llamadas de API saltan el interstitial de ngrok con el header
  `ngrok-skip-browser-warning` (ya está en `frontend/src/api.js`).

- **Alternativa sin cuenta:** `cloudflared tunnel --url http://localhost:8000`.
  Funciona pero la URL cambia en cada reinicio, así que no sirve para un link que
  dure varios días.

## Docker

El [`Dockerfile`](Dockerfile) de la raíz es multi-stage: compila el frontend, lo
mete dentro del backend y FastAPI lo sirve. Un contenedor, una URL. Sirve tanto
para correrlo local como para deployarlo en cualquier VM con Docker.

```bash
docker compose up --build      # primera vez ~15-20 min
# luego: http://localhost:8000
```
