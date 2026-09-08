import { useEffect, useRef } from "react";
import Message from "./Message";
// Scrollea SOLO el contenedor de mensajes, nunca la página.
function scrollToEnd(el) {
  if (el) el.scrollTop = el.scrollHeight;
}

function TypingIndicator() {
  return (
    <div className="row row--assistant">
      <div className="typing">
        <span className="typing__dot" />
        <span className="typing__dot" />
        <span className="typing__dot" />
        <span className="typing__label">escribiendo...</span>
      </div>
    </div>
  );
}

export default function ChatThread({ messages, loading }) {
  const threadRef = useRef(null);

  useEffect(() => {
    scrollToEnd(threadRef.current);
  }, [messages, loading]);

  return (
    <div className="thread" ref={threadRef}>
      {messages.length === 0 && !loading && (
        <div className="thread__empty">
          Escribe una consulta o elige un ejemplo de la izquierda para ver cómo el
          asistente la clasifica y responde.
        </div>
      )}

      {messages.map((m) => (
        <Message key={m.id} msg={m} />
      ))}

      {loading && <TypingIndicator />}
    </div>
  );
}
