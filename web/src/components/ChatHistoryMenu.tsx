import { useEffect, useRef, useState } from "react";
import { fetchConversations, type ConversationSummary } from "../lib/api";
import { formatRelativeTime } from "../lib/format";

/**
 * Small header dropdown for browsing and reopening past conversations
 * (GET /chat/conversations) or starting a fresh one -- deliberately a
 * lightweight popover, not a full sidebar/page, so it doesn't compete with
 * the chat stream itself.
 */
export function ChatHistoryMenu({
  token,
  onSelectConversation,
  onNewChat,
}: {
  token: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewChat: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (!next || !token) return;
    setLoading(true);
    try {
      setConversations(await fetchConversations(token));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={toggle}
        aria-label="Conversation history"
        aria-expanded={open}
        className="rounded-full p-1.5 text-ink-soft transition-colors hover:bg-bg hover:text-ink cursor-pointer"
      >
        <HistoryIcon />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-10 mt-2 w-72 rounded-xl border border-border bg-surface p-1.5 shadow-lg">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onNewChat();
            }}
            className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-accent-strong transition-colors hover:bg-bg cursor-pointer"
          >
            + New chat
          </button>

          <div className="my-1 border-t border-border" />

          {loading ? (
            <div className="px-3 py-4 text-center text-xs text-ink-faint">Loading…</div>
          ) : !conversations || conversations.length === 0 ? (
            <div className="px-3 py-4 text-center text-xs text-ink-faint">No past conversations yet.</div>
          ) : (
            <ul className="max-h-72 space-y-0.5 overflow-y-auto">
              {conversations.map((c) => (
                <li key={c.conversation_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onSelectConversation(c.conversation_id);
                    }}
                    className="w-full rounded-lg px-3 py-2 text-left transition-colors hover:bg-bg cursor-pointer"
                  >
                    <div className="truncate text-sm text-ink">{c.preview || "New conversation"}</div>
                    <div className="mt-0.5 text-xs text-ink-faint">
                      {formatRelativeTime(c.last_message_at)} · {c.message_count}{" "}
                      {c.message_count === 1 ? "message" : "messages"}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
