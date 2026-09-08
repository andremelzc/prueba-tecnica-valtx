# Frontend: asistente de consultas comerciales

Vite + React. Una sola pantalla: barra lateral con ejemplos + chat single-turn
contra el backend.

## Correr

```bash
npm install
cp .env.example .env          # ajustar VITE_API_URL si el backend no está en :8000
npm run dev                    # http://localhost:5173
```

El backend tiene que estar corriendo (`uvicorn main:app` en `backend/`).

## Cómo funciona

- **Barra lateral "Ejemplos":** 5 consultas reales del CSV (una por categoría +
  un caso `con_humano` vía RAG). Al hacer clic **no llaman al backend**: usan
  respuestas precomputadas de `src/ejemplos.data.json`, para que la demo no
  dependa de la latencia del LLM local. Se regeneran con:

  ```bash
  # desde backend/, con el backend corriendo
  python - <<'PY'
  import json, httpx
  casos = [
    ("faq_estatica","¿Cuál es el plazo para devolver un producto?","chat"),
    ("dato_dinamico","¿Cuál es el precio actual del Producto Alfa?","correo"),
    ("otra_area","¿Cuándo pagan los sueldos este mes?","chat"),
    ("con_humano","Tengo una queja sobre la atención que recibí, ¿con quién hablo?","teléfono"),
    ("con_humano_rag","¿Puedo pagar en cuotas?","chat"),
  ]
  out=[{"id":t,"texto":x,"canal":c,
        "respuesta":httpx.post("http://localhost:8000/consulta",json={"texto":x,"canal":c},timeout=240).json()}
       for t,x,c in casos]
  open("../frontend/src/ejemplos.data.json","w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False,indent=2))
  PY
  ```

- **Caja de texto:** cada envío llama a `POST /consulta` en vivo (single-turn, no
  se manda historial). Una consulta `faq_estatica` puede tardar varios segundos
  (LLM local en CPU), por eso el indicador "escribiendo..." es honesto.

- **Badge de categoría** debajo de cada respuesta: teal `faq_estatica`, ámbar
  `dato_dinamico`, gris `otra_area`, coral `con_humano`.

- **"Ver detalle"** (colapsado): fuente citada, score de confianza, método de
  clasificación (`regla`, `llm`, `rag_baja_confianza`, `rag_sin_fundamento`, etc.),
  si fue duplicado, y el resumen para el revisor (en `con_humano`).

- **Errores:** si el backend no responde (caído / CORS), aparece una burbuja de
  error en el chat, no una pantalla en blanco.

## Config

| var | default | qué es |
|-----|---------|--------|
| `VITE_API_URL` | `http://localhost:8000` | URL del backend |

## Paleta

Fondo gris muy claro, barra lateral azul marino `#0B1F4D`, acento celeste
`#29ABE2` (botón enviar). Los 4 colores de badge son independientes de la marca.
