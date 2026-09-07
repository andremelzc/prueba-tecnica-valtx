import { categoriaInfo } from "../categorias";

export default function CategoryBadge({ categoria }) {
  const info = categoriaInfo(categoria);
  return (
    <span className={`badge badge--${categoria}`} title={info.descripcion}>
      <span className="badge__dot" />
      {info.label}
    </span>
  );
}
