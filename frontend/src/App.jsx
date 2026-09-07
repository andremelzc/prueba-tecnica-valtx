import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatThread from "./components/ChatThread";
import Composer from "./components/Composer";
import { consultar } from "./api";

let nextId = 1;
const uid = () => nextId++;

// Pequeña espera para que el indicador "escribiendo…" también se vea con los
// ejemplos cacheados (si no, aparecería la respuesta de golpe).
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  function pushUser(texto) {
    setMessages((m) => [...m, { id: uid(), role: "user", texto }]);
  }

  // Ejemplo de la barra lateral: respuesta precomputada, NO llama al backend.
  async function handleExample(ej) {
    if (loading) return;
    pushUser(ej.texto);
    setLoading(true);
    await delay(650);
    setMessages((m) => [
      ...m,
      { id: uid(), role: "assistant", data: ej.respuesta, cached: true },
    ]);
    setLoading(false);
  }

  // Consulta escrita: llama al backend real.
  async function handleSend(texto, canal) {
    if (loading) return;
    pushUser(texto);
    setLoading(true);
    try {
      const data = await consultar({ texto, canal });
      setMessages((m) => [...m, { id: uid(), role: "assistant", data }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { id: uid(), role: "error", texto: err.message },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <Sidebar onPick={handleExample} disabled={loading} />
      <main className="chat">
        <header className="chat__header">
          <h1>Asistente de consultas comerciales</h1>
          <p>Clasifica cada consulta en una de 4 categorías y responde según corresponda.</p>
        </header>
        <ChatThread messages={messages} loading={loading} />
        <Composer onSend={handleSend} disabled={loading} />
      </main>
    </div>
  );
}
