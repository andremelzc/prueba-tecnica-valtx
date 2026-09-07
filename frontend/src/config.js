// URL del backend. Nunca hardcodeada.
//  - dev:  VITE_API_URL del .env  (por defecto http://localhost:8000)
//  - prod: si no hay VITE_API_URL, se asume que el backend sirve el frontend
//          desde el mismo origen -> "" hace que fetch use rutas relativas (/consulta)
const fallback = import.meta.env.PROD ? "" : "http://localhost:8000";

export const API_URL = import.meta.env.VITE_API_URL ?? fallback;
