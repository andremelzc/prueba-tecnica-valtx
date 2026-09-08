import { useState } from "react";
import { metodoLabel } from "../categorias";

function Row({ label, children }) {
  return (
    <div className="detail__row">
      <span className="detail__key">{label}</span>
      <span className="detail__val">{children}</span>
    </div>
  );
}

export default function DetailPanel({ data }) {
  const [open, setOpen] = useState(false);
  const pct = Math.round((data.confianza ?? 0) * 100);

  return (
    <div className="detail">
      <button className="detail__toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`detail__chevron ${open ? "detail__chevron--open" : ""}`}>▸</span>
        {open ? "Ocultar detalle" : "Ver detalle"}
      </button>

      {open && (
        <div className="detail__body">
          <Row label="Fuente citada">
            {data.fuente ? data.fuente : <em>(no aplica)</em>}
          </Row>
          <Row label="Confianza">
            <span className="confbar">
              <span className="confbar__track">
                <span className="confbar__fill" style={{ width: `${pct}%` }} />
              </span>
              {data.confianza?.toFixed(3)}
            </span>
          </Row>
          <Row label="Método">
            <code>{data.metodo_clasificacion}</code>: {metodoLabel(data.metodo_clasificacion)}
          </Row>
          <Row label="¿Duplicado?">
            {data.es_duplicado ? "Sí (respuesta servida desde el cache)" : "No"}
          </Row>
          {data.razon && <Row label="Razón">{data.razon}</Row>}
          {data.resumen && <Row label="Resumen p/ revisor">{data.resumen}</Row>}
        </div>
      )}
    </div>
  );
}
