import { EJEMPLOS } from "../ejemplos";
import { categoriaInfo } from "../categorias";

export default function Sidebar({ onPick, disabled }) {
  return (
    <aside className="sidebar">
      <span className="sidebar__brand">Valtx</span>
      <h2 className="sidebar__title">Ejemplos</h2>
      <p className="sidebar__hint">
        Consultas reales, una por categoría. Respuesta precomputada (no llama al
        backend) para la demo.
      </p>

      {EJEMPLOS.map((ej) => (
        <button
          key={ej.id}
          className="example-btn"
          onClick={() => onPick(ej)}
          disabled={disabled}
        >
          <span className="example-btn__cat">
            {categoriaInfo(ej.respuesta.categoria).label}
          </span>
          {ej.texto}
        </button>
      ))}

      <div className="sidebar__foot">
        Lo que escribas en la caja de texto sí consulta al backend real.
      </div>
    </aside>
  );
}
