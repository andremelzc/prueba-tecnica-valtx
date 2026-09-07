import { useState } from "react";

const CANALES = ["chat", "correo", "formulario", "teléfono"];

export default function Composer({ onSend, disabled }) {
  const [texto, setTexto] = useState("");
  const [canal, setCanal] = useState("chat");

  function submit(e) {
    e.preventDefault();
    const t = texto.trim();
    if (!t || disabled) return;
    onSend(t, canal);
    setTexto("");
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      submit(e);
    }
  }

  return (
    <div className="composer">
      <form className="composer__form" onSubmit={submit}>
        <select
          className="composer__canal"
          value={canal}
          onChange={(e) => setCanal(e.target.value)}
          aria-label="Canal de la consulta"
          disabled={disabled}
        >
          {CANALES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <textarea
          className="composer__input"
          placeholder="Escribe tu consulta..."
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={disabled}
        />
        <button className="composer__send" type="submit" disabled={disabled || !texto.trim()}>
          Enviar
        </button>
      </form>
      <p className="composer__note">
        Cada consulta es independiente (single-turn). Una consulta de FAQ puede
        tardar varios segundos: el modelo corre local en CPU.
      </p>
    </div>
  );
}
