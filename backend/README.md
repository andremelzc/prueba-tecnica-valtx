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
├── app/
│   ├── config.py          # categorías, rutas, umbrales (todo overridable por env)
│   ├── schemas.py          # modelos Pydantic de request/response
│   ├── normalization.py    # normalizar / normalizar_match / RecentQueryCache (dedup)
│   ├── rules.py            # reglas por keyword, una lista de patrones por categoría
│   └── classifier.py       # reglas + (siguiente paso) fallback al LLM
├── scripts/
│   ├── eval_clasificador.py # pasa data/consultas_ejemplo.csv por las reglas y tabula
│   └── test_parte1.py       # pruebas rápidas sin dependencias
└── data/
    ├── consultas_ejemplo.csv
    └── documentos_referencia.pdf   # (ver nota abajo)
```

## Cómo correr

```bash
# desde backend/, con el venv activado
python -m scripts.test_parte1        # pruebas
python -m scripts.eval_clasificador  # ver clasificación sobre el CSV de ejemplo
```

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

### Deliberadamente NO construido

- **Corrección ortográfica dedicada.** Los typos ("kiero saber komo debuelvo") no
  matchean reglas y caen al LLM del fallback, que los tolera. Hacer fuzzy-match de
  tokens contra las keywords metía falsos positivos por poco beneficio dado el
  volumen.

## Estado / pendientes

- [x] **Parte 1** — normalización + detección de casi-duplicados + clasificador por reglas
- [ ] Parte 2 — integración del LLM local (llama-cpp) + fallback de clasificación
- [ ] Parte 3 — RAG (indexado del documento en Qdrant + embeddings e5)
- [ ] Parte 4 — endpoint `POST /consulta` completo + registro en SQLite + CORS

> **Nota sobre el documento de referencia:** el enunciado pide indexar
> `documentos_referencia.docx`, pero el archivo entregado es un PDF y en
> `requirements.txt` solo está `python-docx` (sin lector de PDF). Para la Parte 3
> hará falta el `.docx` (o añadir un extractor de PDF). Por ahora queda copiado
> en `data/` como referencia.
