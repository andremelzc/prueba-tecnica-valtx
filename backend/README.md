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
│   ├── indexing.py         # .docx -> chunks (párrafos + filas de tabla legibles)
│   ├── rag.py              # embeddings e5 + Qdrant local + búsqueda + generación
│   └── pipeline.py         # orquestación: normalizar → dedup → clasificar → RAG/respuesta
├── scripts/
│   ├── descargar_modelo.py  # baja el GGUF a models/ (una vez)
│   ├── eval_clasificador.py # CSV por las reglas (sin LLM)
│   ├── eval_pipeline.py     # CSV por el pipeline completo (reglas + LLM + RAG)
│   ├── test_parte1.py       # pruebas normalización + reglas
│   ├── test_parte2.py       # pruebas fallback LLM (con LLM falso, sin modelo)
│   └── test_parte3.py       # pruebas indexing + umbral/compuerta RAG (sin modelo)
├── models/                 # Phi-3-mini-4k-instruct-q4.gguf (no versionado)
└── data/
    ├── consultas_ejemplo.csv
    ├── documentos_referencia.docx
    └── qdrant/             # índice vectorial local (no versionado)
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

`python -m scripts.eval_pipeline` — reglas + Phi-3-mini + RAG:

| categoría final | n  |
|-----------------|----|
| faq_estatica    | 35 |
| con_humano      | 25 |
| dato_dinamico   | 11 |
| otra_area       | 9  |

| método de clasificación | n  |
|-------------------------|----|
| `regla`                 | 65 |
| `llm`                   | 9  |
| `rag_sin_fundamento`    | 4  |
| `rag_baja_confianza`    | 2  |
| `llm_fallback_error`    | 0  |

**Cómo llegaron las 25 a `con_humano`:**

| vía | n | ejemplos |
|-----|---|----------|
| regla / LLM directo (queja, excepción, negociación, vago) | 19 | reembolso usado, negociar pago, "hablar con alguien" |
| `rag_baja_confianza` (score < umbral, sin llamar al LLM)  | 2  | certificaciones de calidad, confidencialidad de datos |
| `rag_sin_fundamento` (RAG buscó, el doc no lo cubre)      | 4  | pagar en cuotas, soporte post-venta, envíos a provincia, SLA |

- **Pasos 9-10 cumplidos:** las preguntas de info que el doc no cubre (cuotas,
  soporte, envíos...) ya no las manda el LLM directo a `con_humano`; pasan por
  `faq_estatica` → RAG y el filtro de confianza las deriva por similitud real.
- **Phi-3-mini clasifica: 0 errores de parseo** gracias a la gramática GBNF.
- Costo: clasificación ~5-7 s; cada `faq_estatica` hace 2 llamadas (compuerta +
  generación) → ~60-90 s en CPU. Las 80 en ~13 min (con GPU o modelo más chico, <1 min).

### Ejemplos de respuestas RAG

La fuente va en el campo `fuente` de la respuesta (no siempre dentro del texto:
Phi-3-mini no añade el "(Fuente: …)" de forma fiable).

> **¿Cuál es el plazo para devolver un producto?**  · score 0.91 · fuente: *Política de devoluciones y garantías*
> "El plazo para devolver un producto es de 15 días calendario desde la recepción del mismo."

> **¿Puedo cancelar una solicitud ya enviada?**  · score 0.91 · fuente: *Preguntas frecuentes*
> "Sí, puedes cancelar una solicitud ya enviada antes de que haya sido aprobada.
> Para hacerlo, debes acceder al portal interno y proceder con los pasos necesarios…"

> **¿El Producto Alfa viene con garantía extendida?**  · score 0.86 · fuente: *Catálogo de productos*
> "No, el Producto Alfa (COD-ALF) no viene con garantía extendida. La garantía
> estándar es de 12 meses y cubre defectos de fábrica durante ese período."

Limitaciones observadas: Phi-3-mini a veces ignora el "sin listas" y responde con
pasos numerados (contenido correcto, formato no ideal), y algún caso límite de
"tiempo" (entrega vs. SLA) queda inconsistente. Ambos mejoran con un modelo mayor.

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

### RAG (Parte 3)

- **Chunking:** un chunk por ítem de párrafo + uno por fila de tabla (convertida
  a frase legible) + un chunk-resumen por tabla. El resumen es necesario para
  preguntas que necesitan todas las filas juntas ("¿qué incluye el catálogo?").
- **e5-small comprime los scores de similitud** a un rango muy estrecho
  (~0.81–0.93 para todo), así que un único umbral no separa bien "está en el doc"
  de "no está". Filtro en **dos etapas**: (1) umbral de score (descarta lo
  claramente irrelevante) y (2) **compuerta SÍ/NO del LLM** sobre el contexto
  recuperado (con gramática), + un backstop por regex sobre la 1ª frase de la
  respuesta ("no se menciona en el contexto..."). Mejora natural: e5-base/large o
  un reranker cross-encoder.
- **Grounding:** el prompt de generación pide responder solo con el contexto; si
  el LLM no puede, cae a `con_humano` (`rag_sin_fundamento`). Con score bajo ni
  siquiera se llama al LLM (`rag_baja_confianza`).
- **Ajuste al clasificador (pasos 9-10):** las preguntas de *información* sobre
  producto/servicio/condiciones (cuotas, soporte, envíos, certificaciones) ahora
  van a `faq_estatica` → RAG, y el filtro de confianza las deriva a `con_humano`
  "por el camino correcto" (similitud real, no adivinanza del LLM). Las quejas /
  excepciones / negociaciones siguen yendo directo a `con_humano` (keywords fuertes).

### Deliberadamente NO construido

- **Corrección ortográfica dedicada.** Los typos ("kiero saber komo debuelvo") no
  matchean reglas y caen al LLM del fallback, que los tolera. Hacer fuzzy-match de
  tokens contra las keywords metía falsos positivos por poco beneficio dado el
  volumen.
- **Reranker / embedding grande.** Con e5-small + Phi-3-mini el filtro de 2 etapas
  alcanza para la demo; un cross-encoder o e5-large afinaría la precisión del RAG.

## Estado / pendientes

- [x] **Parte 1** — normalización + detección de casi-duplicados + clasificador por reglas
- [x] **Parte 2** — LLM local (llama-cpp, carga única) + fallback de clasificación
      con salida JSON y manejo de errores; respuestas fijas de `dato_dinamico` y
      `otra_area`; placeholders para `faq_estatica` (RAG) y `con_humano` (resumen)
- [x] **Parte 3** — RAG: indexado del `.docx` en Qdrant local + embeddings e5;
      búsqueda top-5 + filtro de confianza en 2 etapas; generación fundamentada
      con cita de fuente; ajuste del clasificador (info → RAG, quejas → humano)
- [ ] Parte 4 — endpoint `POST /consulta` + registro en SQLite + CORS + resumen `con_humano`
