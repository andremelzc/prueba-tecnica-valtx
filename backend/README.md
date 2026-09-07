# Backend — Asistente de consultas comerciales

Pipeline single-turn (sin memoria entre turnos) que recibe una consulta por
`POST /consulta`, la clasifica en una de 4 intenciones y responde según la
categoría.

## Flujo

```
texto, canal
   │
   ▼
normalización  ──►  ¿casi-duplicado de una consulta reciente? (rapidfuzz)
   │                    └─ sí → devuelve la respuesta cacheada (es_duplicado=true),
   │                            sin reclasificar ni llamar al LLM
   ▼
clasificación de intención
   ├─ reglas por keyword (casos obvios)
   └─ fallback al LLM local (solo lo ambiguo)
   │
   ▼
según categoría
   ├─ faq_estatica  → RAG sobre documentos_referencia (Qdrant + e5) → respuesta LLM citando fuente
   │                  (si el score < umbral → con_humano, no se inventa)
   ├─ dato_dinamico → mensaje fijo: ese dato vive en el sistema comercial
   ├─ otra_area     → mensaje fijo: derivación al área correspondiente
   └─ con_humano    → resumen breve con el LLM, se guarda como pendiente
   │
   ▼
registro en SQLite  →  { categoria, respuesta, fuente, confianza }
```

## Categorías

| Categoría        | Qué cubre                                                        | Cómo se responde                        |
|------------------|-----------------------------------------------------------------|-----------------------------------------|
| `faq_estatica`   | cómo solicitar, plazos, garantía, políticas, catálogo           | RAG + LLM citando la fuente             |
| `dato_dinamico`  | precio, stock, promociones, tipo de cambio                      | mensaje fijo (nunca LLM)                |
| `otra_area`      | fuera del alcance comercial (RRHH, TI, sueldos)                 | mensaje fijo de derivación             |
| `con_humano`     | quejas, negociaciones, excepciones, casos especiales            | resumen con LLM + pendiente en SQLite   |

## Estructura

```
backend/
├── main.py                 # app FastAPI: lifespan carga el LLM 1 vez + /health
├── app/
│   ├── config.py           # categorías, rutas, umbrales, mensajes fijos (overridable por env)
│   ├── schemas.py          # modelos Pydantic de request/response
│   ├── normalization.py    # normalizar / normalizar_match / RecentQueryCache (dedup)
│   ├── rules.py            # reglas por keyword, una lista de patrones por categoría
│   ├── classifier.py       # reglas (scoring + margen) + fallback al LLM
│   ├── llm.py              # carga del GGUF (singleton) + clasificación de intención por LLM
│   └── pipeline.py         # orquestación: normalizar → dedup → clasificar → respuesta
├── scripts/
│   ├── descargar_modelo.py  # baja el GGUF a models/ (una vez)
│   ├── eval_clasificador.py # CSV por las reglas (sin LLM)
│   ├── eval_pipeline.py     # CSV por el pipeline completo (reglas + LLM)
│   ├── test_parte1.py       # pruebas normalización + reglas
│   └── test_parte2.py       # pruebas fallback LLM (con LLM falso, sin modelo)
├── models/                 # Phi-3-mini-4k-instruct-q4.gguf (no versionado)
└── data/
    ├── consultas_ejemplo.csv
    └── documentos_referencia.docx
```

## Cómo correr

```bash
# desde backend/, con el venv activado
python -m scripts.descargar_modelo   # baja el modelo GGUF (~2.4 GB) a models/
python -m scripts.test_parte1        # pruebas Parte 1
python -m scripts.test_parte2        # pruebas Parte 2 (no necesita el modelo)
python -m scripts.eval_pipeline      # CSV por el pipeline completo (necesita el modelo)
SKIP_LLM=1 python -m scripts.eval_pipeline   # sin LLM (los ambiguos -> con_humano)

uvicorn main:app --reload            # levanta la app (carga el LLM al iniciar)
```

## Resultados sobre la muestra de 80 consultas (pipeline completo)

`python -m scripts.eval_pipeline` — reglas + fallback real a Phi-3-mini:

| categoría final | n  |
|-----------------|----|
| faq_estatica    | 37 |
| con_humano      | 23 |
| dato_dinamico   | 11 |
| otra_area       | 9  |

| método      | n  |
|-------------|----|
| `regla`     | 67 (84 %) |
| `llm`       | 13 (16 %) |
| `llm_fallback_error` | 0 |

- El split reglas/LLM (~84/16) coincide con la estimación hecha a mano en el Paso 1.
- El LLM tiende a mandar lo vago a `con_humano` (11 de 13), por la instrucción
  "si dudas, escala". Eso sube `con_humano` de ~12 (solo reglas) a 23. Varias de
  esas (cuotas, soporte, certificaciones, envíos) podrían ir a `faq_estatica` y
  dejar que el umbral de confianza del RAG (Paso 3) decida — el resultado final
  para el usuario es equivalente.
- **0 errores de parseo:** Phi-3-mini por sí solo NO respeta el esquema JSON
  (inventa `{"intent": ..., "command": ...}`); se resuelve con una **gramática
  GBNF** que obliga la forma `{"categoria": <una de 4>, "razon": "..."}`. El
  camino de error (`con_humano` + `llm_fallback_error`) sigue cubierto por
  `test_parte2` con un LLM falso.
- Costo: ~5-7 s por llamada al LLM en CPU; las 80 consultas en ~80 s (solo 13
  tocan el LLM, el resto son reglas ~instantáneas).

## Supuestos y decisiones

- **Calibración del clasificador:** las reglas y sus pesos se calibraron contra la
  muestra de 80 consultas entregada (`data/consultas_ejemplo.csv`). En producción
  requerirían validación continua con el equipo comercial, ya que la distribución
  real de categorías podría diferir. No se persigue el 100 % de cobertura sobre
  esas 80 filas: lo que las reglas no resuelven con margen claro se difiere al LLM
  a propósito.
- **Dedup:** ventana global en memoria (todos los canales, sin user/session id).
  Es una optimización de rendimiento; la fuente de verdad es el log en SQLite. Un
  casi-duplicado devuelve la respuesta ya calculada tal cual (`es_duplicado=true`).
- **`canal` no influye en la clasificación:** la misma consulta se clasifica igual
  venga por donde venga (predecible y testeable). Un sesgo por canal sería una
  regla de negocio explícita a agregar después.
- **Campos extra en la respuesta** (`es_duplicado`, `metodo_clasificacion`): el
  contrato del enunciado es un mínimo; estos campos alimentan el panel de detalle
  del frontend (regla vs LLM, marca de duplicado).

- **Fallback LLM solo para lo ambiguo.** Las reglas resuelven ~84 % de la muestra;
  el LLM (Phi-3-mini) entra únicamente cuando no hay margen claro. Si el LLM
  alucina una categoría o el JSON no parsea, se cae a `con_humano`
  (`metodo_clasificacion="llm_fallback_error"`): ante la incertidumbre, escalar de
  más es más barato que responder mal.
- **`dato_dinamico` nunca pasa por el LLM.** Responde siempre con un mensaje fijo
  que deriva al sistema comercial.

### Deliberadamente NO construido

- **Corrección ortográfica dedicada.** Los typos ("kiero saber komo debuelvo") no
  matchean reglas y caen al LLM del fallback, que los tolera. Hacer fuzzy-match de
  tokens contra las keywords metía falsos positivos por poco beneficio dado el
  volumen.

## Estado / pendientes

- [x] **Parte 1** — normalización + detección de casi-duplicados + clasificador por reglas
- [x] **Parte 2** — LLM local (llama-cpp, carga única) + fallback de clasificación
      con salida JSON y manejo de errores; respuestas fijas de `dato_dinamico` y
      `otra_area`; placeholders para `faq_estatica` (RAG) y `con_humano` (resumen)
- [ ] Parte 3 — RAG (indexado del `.docx` en Qdrant + embeddings e5)
- [ ] Parte 4 — endpoint `POST /consulta` + registro en SQLite + CORS + resumen `con_humano`
