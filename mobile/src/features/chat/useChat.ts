import * as SecureStore from "expo-secure-store";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchConversation,
  fetchConversations,
  streamChatMessage,
  type AnswerParts,
  type ConversationMessage,
  type GoalProposal,
  type Rating,
  type TurnUsage,
} from "@/lib/api";
import { resolveGoalProposal } from "@/lib/goalProposal";
import { useSession } from "@/lib/session";

// SecureStore rejects ":" (the web localStorage key uses one). Dots and hyphens are fine.
const LAST_CONVERSATION_KEY = "bankr.last-conversation-id";

function readLastConversationId(): string | null {
  try {
    return SecureStore.getItem(LAST_CONVERSATION_KEY);
  } catch {
    return null;
  }
}

export type ChatItem =
  | { kind: "user"; id: string; text: string }
  | {
      kind: "assistant";
      id: string;
      text: string;
      parts: AnswerParts;
      goalProposal: GoalProposal | null;
      usage?: TurnUsage | null;
      // The saved reply, for thumbs up/down, and the rating it already has.
      messageId: string;
      feedback?: Rating | null;
    };

let nextId = 0;
const makeId = () => `m${++nextId}`;

/** A reply's goal card, by the same rule as the web app: none when it already has an action card. */
function goalCard(userText: string, assistantText: string, parts: AnswerParts): GoalProposal | null {
  if (parts.action_proposal) return null;
  return resolveGoalProposal({ userText, assistantText, apiProposal: parts.goal_proposal });
}

function partsOf(m: AnswerParts): AnswerParts {
  return {
    sources: m.sources ?? [],
    citations: m.citations,
    uncited_figures: m.uncited_figures,
    goal_proposal: m.goal_proposal ?? null,
    action_proposal: m.action_proposal,
    charts: m.charts,
    links: m.links,
    clarify: m.clarify,
    records: m.records,
  };
}

function itemsFromMessages(messages: ConversationMessage[]): ChatItem[] {
  return messages.map((m, index): ChatItem => {
    if (m.role === "user") return { kind: "user", id: makeId(), text: m.content };
    const previous = messages[index - 1];
    const parts = partsOf(m);
    return {
      kind: "assistant",
      id: makeId(),
      text: m.content,
      parts,
      goalProposal: goalCard(previous?.role === "user" ? previous.content : "", m.content, parts),
      messageId: m.id,
      feedback: m.feedback,
    };
  });
}

/**
 * One chat thread: sending streams the reply in (status line first, then the
 * text as it's written), stop cancels the turn, and a past conversation can be
 * loaded by id. Mirrors the web HomePage's chat state, minus voice.
 */
export function useChat() {
  const { token, signOut } = useSession();
  const [items, setItems] = useState<ChatItem[]>([]);
  // Same key as the web app: seeded so the persist effect doesn't wipe it
  // before restore runs. If this device has never opened a chat, restore
  // falls through to the newest conversation on the server.
  const [conversationId, setConversationId] = useState<string | null>(readLastConversationId);
  const [isSending, setIsSending] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [replySoFar, setReplySoFar] = useState("");
  const [failed, setFailed] = useState<{ itemId: string; text: string; stopped: boolean } | null>(null);
  const turnAbort = useRef<AbortController | null>(null);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!token || !text || isSending) return;
      const itemId = makeId();
      setItems((prev) => [...prev, { kind: "user", id: itemId, text }]);
      setFailed(null);
      setIsSending(true);
      const abort = new AbortController();
      turnAbort.current = abort;
      try {
        const response = await streamChatMessage(token, text, conversationId, setStatusLabel, setReplySoFar, abort.signal);
        setConversationId(response.conversation_id);
        const parts = partsOf(response);
        setItems((prev) => [
          ...prev,
          {
            kind: "assistant",
            id: makeId(),
            text: response.reply,
            parts,
            goalProposal: goalCard(text, response.reply, parts),
            usage: response.usage,
            messageId: response.message_id,
          },
        ]);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return signOut();
        setFailed({ itemId, text, stopped: abort.signal.aborted });
      } finally {
        if (turnAbort.current === abort) turnAbort.current = null;
        setIsSending(false);
        setStatusLabel(null);
        setReplySoFar("");
      }
    },
    [token, conversationId, isSending, signOut]
  );

  const stop = useCallback(() => turnAbort.current?.abort(), []);

  /** Drop the failed question; "retry" asks it again, "edit" returns its text for the composer. */
  const resolveFailed = useCallback(
    (action: "retry" | "edit"): string | null => {
      if (!failed) return null;
      setItems((prev) => prev.filter((i) => i.id !== failed.itemId));
      setFailed(null);
      if (action === "retry") {
        send(failed.text);
        return null;
      }
      return failed.text;
    },
    [failed, send]
  );

  const startNew = useCallback(() => {
    turnAbort.current?.abort();
    setItems([]);
    setConversationId(null);
    setFailed(null);
  }, []);

  const open = useCallback(
    async (id: string) => {
      if (!token) return;
      turnAbort.current?.abort();
      setFailed(null);
      try {
        const messages = await fetchConversation(token, id);
        setConversationId(id);
        setItems(itemsFromMessages(messages));
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) signOut();
      }
    },
    [token, signOut]
  );

  useEffect(() => {
    if (conversationId) SecureStore.setItemAsync(LAST_CONVERSATION_KEY, conversationId).catch(() => {});
    else SecureStore.deleteItemAsync(LAST_CONVERSATION_KEY).catch(() => {});
  }, [conversationId]);

  // Restore the thread this device last had open, or the newest one on the
  // server (so chats started on web show up here without picking history).
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        if (conversationId) {
          try {
            const messages = await fetchConversation(token, conversationId);
            if (cancelled) return;
            setItems(itemsFromMessages(messages));
            setFailed(null);
            return;
          } catch (err) {
            if (err instanceof ApiError && err.status === 401) return signOut();
            if (cancelled) return;
            setConversationId(null);
          }
        }
        const list = await fetchConversations(token);
        if (cancelled || list.length === 0) return;
        const messages = await fetchConversation(token, list[0].conversation_id);
        if (cancelled) return;
        setConversationId(list[0].conversation_id);
        setItems(itemsFromMessages(messages));
        setFailed(null);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) signOut();
      }
    })();
    return () => {
      cancelled = true;
    };
    // Restore once per sign-in, not every time the active id changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, signOut]);

  return { items, isSending, statusLabel, replySoFar, failed, send, stop, resolveFailed, startNew, open };
}
