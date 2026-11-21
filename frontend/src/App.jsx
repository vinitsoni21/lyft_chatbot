import { useState, useRef, useEffect } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function newSessionId() {
  return "s-" + Math.random().toString(36).slice(2, 10);
}

export default function App() {
  const [sessionId] = useState(newSessionId); // new session on every page load
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);

    try {
      const body = { session_id: sessionId, message: text };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();

      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: data.reply, metadata: data.metadata },
        ]);
      } else {
        let msg = "Something went wrong. Please try again.";
        if (res.status === 503) msg = "All providers are unavailable right now. Please try again shortly.";
        else if (res.status === 422) msg = "Invalid input. Please check your message.";
        setMessages((m) => [...m, { role: "error", content: msg }]);
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: "error", content: "Cannot reach the server. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="app">
      <h1>LLM Chatbot</h1>

      <input
        data-testid="system-prompt-input"
        className="system-prompt"
        placeholder="Optional system prompt for this session"
        value={systemPrompt}
        onChange={(e) => setSystemPrompt(e.target.value)}
      />

      <div className="chat">
        {messages.length === 0 && (
          <p className="empty">Send a message to start the conversation.</p>
        )}

        {messages.map((m, i) => {
          if (m.role === "user") {
            return (
              <div key={i} className="bubble user">
                {m.content}
              </div>
            );
          }
          if (m.role === "error") {
            return (
              <div key={i} className="bubble error">
                {m.content}
              </div>
            );
          }
          const meta = m.metadata;
          return (
            <div key={i} className="bubble assistant" data-testid="assistant-message">
              <div className="reply">{m.content}</div>
              <div className="meta">
                <span data-testid="meta-source">{meta.resolution_source}</span>
                <span data-testid="meta-model">{meta.model}</span>
                <span data-testid="meta-latency">{meta.latency_ms} ms</span>
                <span>
                  in: <span data-testid="meta-input-tokens">{meta.input_tokens}</span>
                </span>
                <span>
                  out: <span data-testid="meta-output-tokens">{meta.output_tokens}</span>
                </span>
              </div>
            </div>
          );
        })}

        {loading && <div className="bubble assistant typing">Thinking...</div>}
        <div ref={bottomRef} />
      </div>

      <div className="composer">
        <textarea
          data-testid="chat-input"
          rows={2}
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button data-testid="send-button" onClick={send} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  );
}