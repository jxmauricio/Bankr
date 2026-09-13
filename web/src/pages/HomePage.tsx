import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  fetchConversation,
  fetchGoalProgress,
  fetchIncome,
  fetchNetWorth,
  fetchRollup,
  fetchSpending,
  sendChatMessage,
  type ChatSource,
  type GoalProgress,
  type GoalProposal,
  type ItemizedTransactions,
  type PeriodRollup,
} from "../lib/api";
import { resolveGoalProposal } from "../lib/goalProposal";
import { GoalSidebar } from "../components/GoalSidebar";
import { GoalPaceTrack } from "../components/GoalPaceTrack";
import { GoalProposalCard } from "../components/GoalProposalCard";
import { StatsBar } from "../components/StatsBar";
import { NetWorthFlowModal } from "../components/NetWorthFlowModal";
import { TransactionSearchModal } from "../components/TransactionSearchModal";
import { ChatHistoryMenu } from "../components/ChatHistoryMenu";
import { SlotNumber } from "../components/SlotNumber";
import { useSession } from "../lib/session";
import { useVoiceMode } from "../lib/useVoiceMode";
import { formatDate, formatMoney } from "../lib/format";
import { AssistantText } from "../components/AssistantText";

const GREETING = "Ask me anything about your money — what you've spent, what's coming in, or whether you're on pace for your goal.";
// Not scoped to a user/token: a different account landing on a stale id
// just 404s inside loadConversation and falls back to the greeting, same as
// the id being gone for any other reason.
const LAST_CONVERSATION_KEY = "bankr:last-conversation-id";

type Period = "week" | "month" | "year";
type Topic = "spending" | "income";

type StreamItem =
  | { kind: "assistant-text"; id: string; text: string; sources?: ChatSource[]; goalProposal?: GoalProposal | null }
  | { kind: "user-text"; id: string; text: string }
  | { kind: "topic-card"; id: string; topic: Topic; period: Period };

let nextId = 0;
const makeId = () => `item-${nextId++}`;

export function HomePage() {
  const { token, signOut } = useSession();
  const [netWorth, setNetWorth] = useState<number | null>(null);
  const [monthRollup, setMonthRollup] = useState<PeriodRollup | null>(null);
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [items, setItems] = useState<StreamItem[]>([{ kind: "assistant-text", id: makeId(), text: GREETING }]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFlow, setShowFlow] = useState(false);
  const [statTileGroup, setStatTileGroup] = useState<Topic | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const { voiceMode, voiceState, toggle: toggleVoiceMode, speakReply } = useVoiceMode({
    onFinalTranscript: (text) => ask(text),
    onDraftChange: setDraft,
    onError: setError,
  });

  useEffect(() => {
    if (!token) return;
    fetchNetWorth(token).then((nw) => setNetWorth(nw.current));
    fetchRollup(token, "month").then(setMonthRollup);
    fetchGoalProgress(token).then((progress) => setGoals(progress.goals ?? []));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function refreshGoalProgress() {
    if (!token) return;
    const progress = await fetchGoalProgress(token);
    setGoals(progress.goals ?? []);
  }

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [items, isSending]);

  // Keep the active conversation in sync with localStorage so a refresh (or
  // reopening the tab) restores it instead of dropping back to the greeting.
  useEffect(() => {
    if (conversationId) localStorage.setItem(LAST_CONVERSATION_KEY, conversationId);
    else localStorage.removeItem(LAST_CONVERSATION_KEY);
  }, [conversationId]);

  function pushItem(item: StreamItem) {
    setItems((prev) => [...prev, item]);
  }

  async function ask(text: string) {
    if (!token || !text.trim() || isSending) return;
    pushItem({ kind: "user-text", id: makeId(), text });
    setError(null);
    setIsSending(true);
    try {
      const response = await sendChatMessage(token, text, conversationId);
      setConversationId(response.conversation_id);
      pushItem({
        kind: "assistant-text",
        id: makeId(),
        text: response.reply,
        sources: response.sources,
        goalProposal: resolveGoalProposal({
          userText: text,
          assistantText: response.reply,
          apiProposal: response.goal_proposal,
        }),
      });
      speakReply(response.reply);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bankr couldn't respond. Try again.");
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    await ask(text);
  }

  function showTopic(topic: Topic) {
    pushItem({ kind: "topic-card", id: makeId(), topic, period: "month" });
  }

  async function loadConversation(id: string, { silent = false }: { silent?: boolean } = {}) {
    if (!token) return;
    if (!silent) setError(null);
    try {
      const messages = await fetchConversation(token, id);
      setItems(
        messages.map((m, index) => {
          if (m.role === "user") {
            return { kind: "user-text" as const, id: makeId(), text: m.content };
          }
          const previous = messages[index - 1];
          return {
            kind: "assistant-text" as const,
            id: makeId(),
            text: m.content,
            sources: m.sources,
            goalProposal: resolveGoalProposal({
              userText: previous?.role === "user" ? previous.content : "",
              assistantText: m.content,
              apiProposal: m.goal_proposal,
            }),
          };
        }),
      );
      setConversationId(id);
    } catch (err) {
      // Stale/foreign id (e.g. a different account, or it's gone) --
      // silently drop back to the greeting on the restore-on-refresh path
      // instead of surfacing an error for something the user didn't ask for.
      localStorage.removeItem(LAST_CONVERSATION_KEY);
      if (!silent) setError(err instanceof ApiError ? err.message : "Couldn't load that conversation.");
    }
  }

  // Restore the conversation that was active last time, if any, so a
  // refresh (or reopening the tab) lands back where the user left off.
  useEffect(() => {
    if (!token) return;
    const savedId = localStorage.getItem(LAST_CONVERSATION_KEY);
    if (savedId) loadConversation(savedId, { silent: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function startNewChat() {
    setError(null);
    setConversationId(null);
    setItems([{ kind: "assistant-text", id: makeId(), text: GREETING }]);
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <span className="font-display text-xl font-semibold text-ink">Bankr</span>
        <div className="flex items-center gap-4">
          <span className="font-tabular text-sm text-ink-soft">
            {netWorth !== null ? <SlotNumber value={formatMoney(netWorth)} /> : "—"}
            <span className="ml-1.5 font-body text-ink-faint">net worth</span>
          </span>
          <ChatHistoryMenu token={token} onSelectConversation={loadConversation} onNewChat={startNewChat} />
          <button
            type="button"
            onClick={signOut}
            className="text-sm text-ink-soft transition-colors hover:text-ink cursor-pointer"
          >
            Sign out
          </button>
        </div>
      </header>

      {showFlow && token && (
        <NetWorthFlowModal token={token} netWorth={netWorth} onClose={() => setShowFlow(false)} />
      )}

      {statTileGroup && token && (
        <TransactionSearchModal token={token} group={statTileGroup} onClose={() => setStatTileGroup(null)} />
      )}

      <div className="flex flex-1 overflow-hidden">
        <GoalSidebar goals={goals} />

        <div className="flex flex-1 flex-col overflow-hidden">
          <div ref={streamRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
            <div className="mx-auto flex max-w-2xl flex-col gap-4">
              <StatsBar
                netWorth={netWorth}
                rollup={monthRollup}
                onNetWorthClick={() => setShowFlow(true)}
                onIncomeClick={() => setStatTileGroup("income")}
                onSpendingClick={() => setStatTileGroup("spending")}
              />
              {goals.length > 0 && (
                <div className="flex flex-col gap-3 lg:hidden">
                  {goals.map((goal) => (
                    <GoalPaceTrack key={goal.id} progress={goal} />
                  ))}
                </div>
              )}
              {items.map((item) => (
                <StreamEntry
                  key={item.id}
                  item={item}
                  token={token}
                  onGoalCreated={refreshGoalProgress}
                />
              ))}
              {isSending && (
                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-bl-sm border-l-2 border-gold bg-surface px-4 py-3">
                    <ThinkingIndicator />
                  </div>
                </div>
              )}
              {error && (
                <p role="alert" className="text-sm text-danger">
                  {error}
                </p>
              )}
            </div>
          </div>

          <div className="mx-auto flex w-full max-w-2xl shrink-0 flex-wrap gap-2 px-6 pb-3">
            <Chip label="Spending this month" onClick={() => showTopic("spending")} />
            <Chip label="Income this month" onClick={() => showTopic("income")} />
            <Chip label="Am I on pace for my goal?" onClick={() => ask("Am I on pace for my goal?")} />
          </div>

          <form
            onSubmit={handleSubmit}
            className="mx-auto flex w-full max-w-2xl shrink-0 items-center gap-2 border-t border-border px-6 py-4"
          >
            <button
              type="button"
              onClick={toggleVoiceMode}
              aria-label={voiceMode ? "Stop voice mode" : "Start voice mode"}
              aria-pressed={voiceMode}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors cursor-pointer ${
                voiceState === "listening"
                  ? "bg-danger-soft text-danger animate-pulse"
                  : voiceState === "speaking"
                    ? "bg-gold-soft text-gold"
                    : voiceMode
                      ? "bg-accent-soft text-accent-strong"
                      : "text-ink-soft hover:bg-bg hover:text-ink"
              }`}
            >
              <MicIcon />
            </button>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                voiceState === "listening"
                  ? "Listening…"
                  : voiceState === "speaking"
                    ? "Bankr is speaking…"
                    : "Ask about your money"
              }
              aria-label="Ask about your money"
              className="flex-1 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-accent"
            />
            <button
              type="submit"
              disabled={isSending || !draft.trim()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-transform hover:scale-105 disabled:opacity-40 disabled:hover:scale-100 cursor-pointer"
              aria-label="Send"
            >
              <SendIcon />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function StreamEntry({
  item,
  token,
  onGoalCreated,
}: {
  item: StreamItem;
  token: string | null;
  onGoalCreated: () => void | Promise<void>;
}) {
  switch (item.kind) {
    case "assistant-text":
      return (
        <div className="flex flex-col items-start gap-2">
          <div className="max-w-[85%] rounded-2xl rounded-bl-sm border-l-2 border-gold bg-surface px-4 py-2.5 text-sm leading-relaxed text-ink">
            <AssistantText text={item.text} />
          </div>
          {item.sources && item.sources.length > 0 && (
            <div
              className="flex items-center gap-1 px-1 text-[11px] text-ink-faint"
              title="Grounded in your real account data via these lookups"
            >
              <SourceIcon />
              <span>{item.sources.map((s) => s.label).join(" · ")}</span>
            </div>
          )}
          {item.goalProposal && (
            <GoalProposalCard
              token={token}
              proposal={item.goalProposal}
              onCreated={onGoalCreated}
            />
          )}
        </div>
      );
    case "user-text":
      return (
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm leading-relaxed text-white">
            {item.text}
          </div>
        </div>
      );
    case "topic-card":
      return <TopicCard token={token} topic={item.topic} initialPeriod={item.period} />;
  }
}

function TopicCard({
  token,
  topic,
  initialPeriod,
}: {
  token: string | null;
  topic: Topic;
  initialPeriod: Period;
}) {
  const [period, setPeriod] = useState<Period>(initialPeriod);
  const [rollup, setRollup] = useState<PeriodRollup | null>(null);
  const [itemized, setItemized] = useState<ItemizedTransactions | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchRollup(token, period).then(setRollup);
    (topic === "spending" ? fetchSpending(token, period) : fetchIncome(token, period)).then(setItemized);
  }, [token, topic, period]);

  const headline = topic === "spending" ? rollup?.spending : rollup?.income;

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium capitalize text-ink-soft">
          {topic} · {period}
        </h3>
        <div className="flex rounded-full border border-border bg-bg p-0.5 text-xs">
          {(["week", "month", "year"] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={`rounded-full px-2.5 py-1 capitalize transition-colors cursor-pointer ${
                period === p ? "bg-accent text-white" : "text-ink-soft hover:text-ink"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 font-tabular text-2xl font-semibold text-ink">
        {headline !== undefined ? formatMoney(headline) : <SkeletonLine />}
      </div>

      {itemized ? (
        itemized.items.length === 0 ? (
          <p className="mt-4 text-center text-sm text-ink-faint">Nothing here yet for this period.</p>
        ) : (
          <ul className="mt-4 max-h-64 space-y-1 overflow-y-auto">
            {itemized.items.map((entry, i) => (
              <li key={i} className="flex items-center justify-between py-1.5 text-sm">
                <div className="min-w-0">
                  <div className="truncate text-ink">{entry.merchant_name ?? entry.category ?? "Transaction"}</div>
                  <div className="text-xs text-ink-faint">
                    {formatDate(entry.date)} {entry.category && `· ${entry.category}`}
                    {entry.is_pending && " · Pending"}
                  </div>
                </div>
                <span className="font-tabular shrink-0 pl-3 text-ink">{formatMoney(Math.abs(entry.amount))}</span>
              </li>
            ))}
          </ul>
        )
      ) : (
        <div className="mt-4 space-y-2">
          <SkeletonLine />
          <SkeletonLine />
        </div>
      )}
    </div>
  );
}

function Chip({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-border px-3.5 py-1.5 text-sm text-ink-soft transition-colors hover:border-accent hover:bg-accent-soft hover:text-ink cursor-pointer"
    >
      {label}
    </button>
  );
}

function SkeletonLine() {
  return <div className="h-4 animate-pulse rounded bg-bg" />;
}

function SendIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1.5" role="status" aria-label="Bankr is thinking">
      <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-gold [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-gold [animation-delay:160ms]" />
      <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-gold [animation-delay:320ms]" />
    </div>
  );
}

function SourceIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="shrink-0">
      <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
