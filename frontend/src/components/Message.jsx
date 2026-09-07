import CategoryBadge from "./CategoryBadge";
import DetailPanel from "./DetailPanel";

export default function Message({ msg }) {
  if (msg.role === "user") {
    return (
      <div className="row row--user">
        <div className="bubble bubble--user">{msg.texto}</div>
      </div>
    );
  }

  if (msg.role === "error") {
    return (
      <div className="row row--error">
        <div className="bubble bubble--error">⚠️ {msg.texto}</div>
      </div>
    );
  }

  // assistant
  const { data } = msg;
  return (
    <div className="row row--assistant">
      <div className="assistant-block">
        <div className="bubble bubble--assistant">{data.respuesta}</div>
        <div className="msg-meta">
          <CategoryBadge categoria={data.categoria} />
          {msg.cached && <span className="cached-tag">respuesta de ejemplo</span>}
          {data.es_duplicado && <span className="cached-tag">duplicado</span>}
        </div>
        <DetailPanel data={data} />
      </div>
    </div>
  );
}
