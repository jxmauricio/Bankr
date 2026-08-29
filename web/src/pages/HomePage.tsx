import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  fetchGoalProgress,
  fetchIncome,
  fetchNetWorth,
  fetchRollup,
  fetchSpending,
  sendChatMessage,
  type GoalProgress,
  type ItemizedTransactions,
  type PeriodRollup,
} from "../lib/api";
import { GoalSidebar } from "../components/GoalSidebar";
import { GoalPaceTrack } from "../components/GoalPaceTrack";
import { StatsBar } from "../components/StatsBar";
import { NetWorthFlowModal } from "../components/NetWorthFlowModal";
import { TransactionSearchModal } from "../components/TransactionSearchModal";
import { SlotNumber } from "../components/SlotNumber";
import { useSession } from "../lib/session";
import { formatDate, formatMoney } from "../lib/format";
import { AssistantText } from "../components/AssistantText";

type Period = "week" | "month" | "year";
type Topic = "spending" | "income";

type StreamItem =
  | { kind: "assistant-text"; id: string; text: string }
  | { kind: "user-text"; id: string; text: string }
  | { kind: "topic-card"; id: string; topic: Topic; period: Period };

let nextId = 0;
const makeId = () => `item-${nextId++}`;

export function HomePage() {
  const { token, signOut } = useSession();
  const [netWorth, setNetWorth] = useState<number | null>(null);
  const [monthRollup, setMonthRollup] = useState<PeriodRollup | null>(null);
  const [goalProgress, setGoalProgress] = useState<GoalProgress | null>(null);
  const [items, setItems] = useState<StreamItem[]>([
    {
      kind: "assistant-text",
      id: makeId(),
      text: "Ask me anything about your money — what you've spent, what's coming in, or whether you're on pace for your goal.",
    },
  ]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFlow, setShowFlow] = useState(false);
  const [statTileGroup, setStatTileGroup] = useState<Topic | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    fetchNetWorth(token).then((nw) => setNetWorth(nw.current));
    fetchRollup(token, "month").then(setMonthRollup);
    fetchGoalProgress(token).then((progress) => setGoalProgress(progress.type ? progress : null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [items, isSending]);

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
      pushItem({ kind: "assistant-text", id: makeId(), text: response.reply });
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

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <span className="font-display text-xl font-semibold text-ink">Bankr</span>
        <div className="flex items-center gap-4">
          <span className="font-tabular text-sm text-ink-soft">
            {netWorth !== null ? <SlotNumber value={formatMoney(netWorth)} /> : "—"}
            <span className="ml-1.5 font-body text-ink-faint">net worth</span>
          </span>
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
        <GoalSidebar goalProgress={goalProgress} />

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
              {goalProgress && (
                <div className="lg:hidden">
                  <GoalPaceTrack progress={goalProgress} />
                </div>
              )}
              {items.map((item) => (
                <StreamEntry key={item.id} item={item} token={token} />
              ))}
              {isSending && (
                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-bl-sm border-l-2 border-gold bg-surface px-4 py-2.5 text-sm text-ink-soft">
                    Bankr is thinking…
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
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about your money"
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

function StreamEntry({ item, token }: { item: StreamItem; token: string | null }) {
  switch (item.kind) {
    case "assistant-text":
      return (
        <div className="flex justify-start">
          <div className="max-w-[85%] rounded-2xl rounded-bl-sm border-l-2 border-gold bg-surface px-4 py-2.5 text-sm leading-relaxed text-ink">
            <AssistantText text={item.text} />
          </div>
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
