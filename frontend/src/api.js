import { API_URL } from "./config";

/**
 * Envía una consulta al backend. Single-turn: no se manda historial,
 * cada consulta es independiente.
 * @returns {Promise<{categoria,respuesta,fuente,confianza,metodo_clasificacion,es_duplicado,resumen}>}
 */
export async function consultar({ texto, canal }) {
  let res;
  try {
    res = await fetch(`${API_URL}/consulta`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Si el backend se expone por ngrok, evita la pantalla intermedia en
        // las llamadas de API. Inofensivo en cualquier otro caso.
        "ngrok-skip-browser-warning": "true",
      },
      body: JSON.stringify({ texto, canal }),
    });
  } catch {
    // fallo de red / CORS / backend caído
    throw new Error(
      `No pude conectar con el backend (${API_URL}). ¿Está corriendo y con CORS habilitado?`
    );
  }
  if (!res.ok) {
    throw new Error(`El backend respondió ${res.status} ${res.statusText}.`);
  }
  return res.json();
}
