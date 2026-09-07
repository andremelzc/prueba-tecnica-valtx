import { useEffect, useRef } from "react";
import Message from "./Message";

function TypingIndicator() {
  return (
    <div className="row row--assistant">
      <div className="typing">
        <span className="typing__dot" />
        <span className="typing__dot" />
        <span className="typing__dot" />
        <span className="typing__label">escribiendo…</span>
      </div>
    </div>
  );
}

export default function ChatThread({ messages, loading }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="thread">
      {messages.length === 0 && !loading && (
        <div className="thread__empty">
          Escribe una consulta o elegí un ejemplo de la izquierda para ver cómo el
          asistente la clasifica y responde.
        </div>
      )}

      {messages.map((m) => (
        <Message key={m.id} msg={m} />
      ))}

      {loading && <TypingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
