// Metadatos de presentación de las 4 categorías que devuelve el backend.
// Los colores de badge son independientes de la paleta de marca de Valtx.
export const CATEGORIAS = {
  faq_estatica: { label: "FAQ / documento", descripcion: "Respondida con la documentación de referencia" },
  dato_dinamico: { label: "Dato dinámico", descripcion: "Vive en el sistema comercial, no en la documentación" },
  otra_area: { label: "Otra área", descripcion: "Fuera del alcance comercial" },
  con_humano: { label: "Deriva a una persona", descripcion: "Necesita revisión humana" },
};

// Etiquetas legibles para el campo metodo_clasificacion.
export const METODOS = {
  regla: "Reglas por keyword",
  llm: "LLM (fallback de clasificación)",
  llm_fallback_error: "LLM — respuesta no parseable, se escaló",
  rag_baja_confianza: "RAG — similitud por debajo del umbral",
  rag_sin_fundamento: "RAG — el documento no cubre la consulta",
  sin_llm_fallback: "Reglas ambiguas y LLM no disponible",
};

export function categoriaInfo(cat) {
  return CATEGORIAS[cat] || { label: cat, descripcion: "" };
}

export function metodoLabel(m) {
  return METODOS[m] || m;
}
