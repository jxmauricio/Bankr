import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, sendChatMessage } from "../lib/api";
import { useSession } from "../lib/session";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function ChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { token } = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !draft.trim() || isSending) return;
    const text = draft.trim();
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setDraft("");
    setError(null);
    setIsSending(true);
    try {
      const response = await sendChatMessage(token, text, conversationId);
      setConversationId(response.conversation_id);
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bankr couldn't respond. Try again.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/20 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-surface-dark text-white shadow-2xl transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        role="dialog"
        aria-label="Ask Bankr"
      >
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div>
            <h2 className="font-display text-lg font-semibold">Ask Bankr</h2>
            <p className="text-sm text-white/50">Grounded in your real balances and spending.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close chat"
            className="rounded-full p-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-white cursor-pointer"
          >
            <CloseIcon />
          </button>
        </div>

        <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {messages.length === 0 && (
            <div className="mt-8 text-center text-sm text-white/40">
              Try "How much did I spend on dining this month?" or "Am I on pace for my goal?"
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-accent text-white"
                    : "border-l-2 border-gold bg-white/5 text-white/90"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {isSending && <div className="text-sm text-white/40">Bankr is thinking…</div>}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2 border-t border-white/10 p-4">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about your money…"
            className="flex-1 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus:border-accent"
          />
          <button
            type="submit"
            disabled={isSending || !draft.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-50 cursor-pointer"
          >
            Send
          </button>
        </form>
      </div>
    </>
  );
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  );
}
