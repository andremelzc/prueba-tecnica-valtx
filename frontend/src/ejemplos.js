// Respuestas precomputadas del backend (una consulta real por categoría).
// Se generan con backend/scripts o a mano y se guardan en ejemplos.data.json.
// Los botones de la barra lateral usan esto y NO llaman al backend: así la demo
// no depende de la latencia del LLM local.
import data from "./ejemplos.data.json";

export const EJEMPLOS = data;
