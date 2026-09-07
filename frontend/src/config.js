// URL del backend. Nunca hardcodeada: se toma de VITE_API_URL (ver .env.example).
// El fallback solo cubre el caso de desarrollo local sin .env.
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
