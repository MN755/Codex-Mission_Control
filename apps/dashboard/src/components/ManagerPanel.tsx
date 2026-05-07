import { useState } from "react";

export function ManagerPanel({
  managerMode,
  managerModel,
  managerReasoning,
  currentAction,
  reply,
  onSend,
}: {
  managerMode: string;
  managerModel: string;
  managerReasoning: string;
  currentAction: string;
  reply: string;
  onSend: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim()) {
      return;
    }
    setPending(true);
    try {
      await onSend(message);
      setMessage("");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="manager-panel">
      <div className="manager-panel__history">
        <span className="eyebrow">Manager AI</span>
        <h3>Manager channel</h3>
        <div className="manager-panel__meta">
          <span className="header-chip">Mode: {managerMode}</span>
          <span className="header-chip">Model: {managerModel}</span>
          <span className="header-chip">Reasoning: {managerReasoning}</span>
        </div>
        <p className="manager-panel__action">Current action: {currentAction}</p>
        <p>{reply || "The manager will coordinate workers and summarize next actions here."}</p>
      </div>
      <form className="manager-panel__composer" onSubmit={handleSubmit}>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Ask the manager to redirect work, explain the plan, or handle a change request."
        />
        <button disabled={pending}>{pending ? "Sending..." : "Send to manager"}</button>
      </form>
    </div>
  );
}
