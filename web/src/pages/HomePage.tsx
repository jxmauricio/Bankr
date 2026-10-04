import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  fetchConversation,
  fetchGoalProgress,
  fetchIncome,
  fetchLinkedBanks,
  fetchNetWorth,
  fetchRollup,
  fetchSpending,
  resyncAccounts,
  streamChatMessage,
  type ChatSource,
  type GoalProgress,
  type GoalProposal,
  type LinkedBank,
  type ItemizedTransactions,
  type PeriodRollup,
  type SourceQuery,
} from "../lib/api";
import { resolveGoalProposal } from "../lib/goalProposal";
import { GoalSidebar } from "../components/GoalSidebar";
import { GoalPaceTrack } from "../components/GoalPaceTrack";
import { GoalProposalCard } from "../components/GoalProposalCard";
import { CreateGoalModal, NewGoalButton } from "../components/CreateGoalModal";
import { isOAuthReturn } from "../lib/plaidOAuth";
import { AverageBar } from "../components/AverageBar";
import { ProfileMenu } from "../components/ProfileMenu";
import { PeriodFilter } from "../components/PeriodFilter";
import { loadPeriod, savePeriod, type Period as TimePeriod } from "../lib/period";
import { RelinkBanner } from "../components/StatusBanners";
import { SourceBreakdown } from "../components/SourceBreakdown";
import { SettingsModal } from "../components/SettingsModal";
import { NetWorthFlowModal } from "../components/NetWorthFlowModal";
import { TransactionSearchModal } from "../components/TransactionSearchModal";
import { ChatHistoryMenu } from "../components/ChatHistoryMenu";
import { useSession } from "../lib/session";
import { useVoiceMode } from "../lib/useVoiceMode";
import { formatDate, formatMoney } from "../lib/format";
import { AssistantText } from "../components/AssistantText";
import { RowAmount } from "../components/TransactionSearch";

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
// The opening greeting is a placeholder in the list; the starter prompts replace it on screen.
const GREETING_ID = "greeting";

export function HomePage({ onNoBanksLeft }: { onNoBanksLeft: () => void }) {
  const { token, signOut } = useSession();
  const [netWorth, setNetWorth] = useState<number | null>(null);
  const [nwHistory, setNwHistory] = useState<{ date: string; net_worth: number }[]>([]);
  const [nwAsOf, setNwAsOf] = useState<string | null>(null);
  const [accountCount, setAccountCount] = useState<number | undefined>();
  const [excludedCount, setExcludedCount] = useState(0);
  const [banks, setBanks] = useState<LinkedBank[]>([]);
  const [period, setPeriod] = useState<TimePeriod>(loadPeriod);
  const [monthRollup, setMonthRollup] = useState<PeriodRollup | null>(null);
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [creatingGoal, setCreatingGoal] = useState(false);
  // Returning from an OAuth bank's site: reopen Settings so Link can resume.
  const [showSettings, setShowSettings] = useState(isOAuthReturn);
  const [items, setItems] = useState<StreamItem[]>([{ kind: "assistant-text", id: `${GREETING_ID}-${nextId++}`, text: GREETING }]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showFlow, setShowFlow] = useState(false);
  const [sourceQuery, setSourceQuery] = useState<SourceQuery | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const streamRef = useRef<HTMLDivElement>(null);
  const { voiceMode, voiceState, toggle: toggleVoiceMode, speakReply } = useVoiceMode({
    onFinalTranscript: (text) => ask(text),
    onDraftChange: setDraft,
    onError: setError,
  });

  function loadStandingState() {
    if (!token) return Promise.resolve();
    return Promise.all([
      fetchNetWorth(token).then((nw) => {
        setNetWorth(nw.current);
        setNwHistory(nw.history ?? []);
        setNwAsOf(nw.as_of);
        setAccountCount(nw.accounts?.length);
        setExcludedCount(nw.excluded_accounts?.length ?? 0);
      }),
      fetchLinkedBanks(token).then(setBanks).catch(() => setBanks([])),
      fetchRollup(token, "month").then(setMonthRollup),
      fetchGoalProgress(token).then((progress) => setGoals(progress.goals ?? [])),
    ]);
  }

  useEffect(() => {
    loadStandingState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function changePeriod(next: TimePeriod) {
    setPeriod(next);
    savePeriod(next);
  }

  async function refreshFromBank() {
    if (!token || isRefreshing) return;
    setIsRefreshing(true);
    setError(null);
    try {
      await resyncAccounts(token);
      await loadStandingState();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't refresh from your bank. Try again.");
    } finally {
      setIsRefreshing(false);
    }
  }

  async function refreshGoalProgress() {
    if (!token) return;
    const progress = await fetchGoalProgress(token);
    setGoals(progress.goals ?? []);
  }

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [items, isSending, statusLabel]);

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
    setStatusLabel(null);
    try {
      const response = await streamChatMessage(token, text, conversationId, setStatusLabel);
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
      setStatusLabel(null);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    await ask(text);
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
    setItems([{ kind: "assistant-text", id: `${GREETING_ID}-${nextId++}`, text: GREETING }]);
  }

  const brokenBanks = banks.filter((b) => b.status === "error").map((b) => b.institution_name);
  const lastAssistant = [...items].reverse().find((i) => i.kind === "assistant-text");
  const lastAssistantId = lastAssistant?.id;
  const isGreeting = items.length === 1 && Boolean(lastAssistantId?.startsWith(GREETING_ID));
  const composerSuggestions = isSending
    ? []
    : isGreeting
      ? starterPromptsFor(goals)
      : lastAssistant?.kind === "assistant-text"
        ? followUpsFor(lastAssistant)
        : [];

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-[68px] shrink-0 items-center justify-between gap-2 px-4 sm:px-7">
        <div className="flex items-center gap-3">
          <ChatHistoryMenu token={token} onSelectConversation={loadConversation} onNewChat={startNewChat} />
          <span className="font-display text-[21px] font-semibold tracking-tight text-ink">
            bankr<span className="text-signal">_</span>
          </span>
          <span className="hidden rounded-full bg-signal-wash px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] text-signal md:inline">PRIVATE BETA</span>
        </div>
        <div className="flex items-center gap-3">
          <PeriodFilter period={period} onChange={changePeriod} />
          {token && (
            <ProfileMenu
              token={token}
              onOpenSettings={() => setShowSettings(true)}
              onSignOut={signOut}
              attention={brokenBanks.length > 0}
            />
          )}
        </div>
      </header>

      {showFlow && token && (
        <NetWorthFlowModal
          token={token}
          netWorth={netWorth}
          period={period}
          onClose={() => setShowFlow(false)}
        />
      )}

      {sourceQuery && token && (
        <TransactionSearchModal
          token={token}
          group="spending"
          query={sourceQuery}
          onClose={() => setSourceQuery(null)}
        />
      )}

      {showSettings && token && (
        <SettingsModal
          token={token}
          onClose={() => setShowSettings(false)}
          onBanksChanged={async (remaining) => {
            // With no banks left there's nothing to show; let the onboarding
            // gate send the user back to "Link your bank".
            if (remaining === 0) return onNoBanksLeft();
            await loadStandingState();
          }}
          onAccountDeleted={signOut}
        />
      )}

      {creatingGoal && token && (
        <CreateGoalModal
          token={token}
          atLimit={goals.length >= 5}
          onClose={() => setCreatingGoal(false)}
          onCreated={refreshGoalProgress}
        />
      )}

      <div className="flex flex-1 overflow-hidden">
        <GoalSidebar
          goals={goals}
          token={token}
          onGoalDeleted={refreshGoalProgress}
          onCreateGoal={() => setCreatingGoal(true)}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          <div ref={streamRef} className="flex-1 space-y-4 overflow-y-auto px-7 py-3">
            <div className="mx-auto flex max-w-2xl flex-col gap-4">
              {brokenBanks.length > 0 && <RelinkBanner banks={brokenBanks} onManage={() => setShowSettings(true)} />}
              {token && (
                <AverageBar
                  token={token}
                  period={period}
                  netWorth={netWorth}
                  asOf={nwAsOf ?? monthRollup?.as_of}
                  onNetWorthClick={() => setShowFlow(true)}
                  onRefresh={refreshFromBank}
                  isRefreshing={isRefreshing}
                  refreshKey={monthRollup}
                  history={nwHistory}
                  accountCount={accountCount}
                  excludedCount={excludedCount}
                  bankCount={banks.length}
                  showStale={brokenBanks.length === 0}
                />
              )}
              <div className="flex flex-col gap-3 lg:hidden">
                {goals.map((goal) => (
                  <GoalPaceTrack
                    key={goal.id}
                    progress={goal}
                    token={token}
                    onDeleted={refreshGoalProgress}
                  />
                ))}
                <NewGoalButton onClick={() => setCreatingGoal(true)} />
              </div>
              {items.filter((item) => !item.id.startsWith(GREETING_ID)).map((item) => (
                <StreamEntry
                  key={item.id}
                  item={item}
                  token={token}
                  onGoalCreated={refreshGoalProgress}
                  onOpenSource={setSourceQuery}
                  isLast={item.id === lastAssistantId && !item.id.startsWith(GREETING_ID) && !isSending}
                />
              ))}
              {isSending && (
                <div className="flex items-start gap-3">
                  <BotMark />
                  <div className="rounded-[6px_20px_20px_20px] bg-surface px-[18px] py-3.5">
                    <ThinkingIndicator label={statusLabel} />
                  </div>
                </div>
              )}
              {error && (
                <p role="alert" className="text-sm text-negative">
                  {error}
                </p>
              )}
            </div>
          </div>

          <form
            onSubmit={handleSubmit}
            className="mx-auto w-full max-w-2xl shrink-0 px-7 pb-5 pt-2"
          >
            {composerSuggestions.length > 0 && (
              <SuggestionChips suggestions={composerSuggestions} onAsk={ask} />
            )}
            <div className="flex items-center gap-2 rounded-3xl border border-control bg-surface p-1.5 focus-within:border-signal">
            <button
              type="button"
              onClick={toggleVoiceMode}
              aria-label={voiceMode ? "Stop voice mode" : "Start voice mode"}
              aria-pressed={voiceMode}
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors cursor-pointer ${
                voiceState === "listening"
                  ? "bg-negative-soft text-negative animate-pulse"
                  : voiceState === "speaking"
                    ? "bg-warn-soft text-warn"
                    : voiceMode
                      ? "bg-signal-wash text-signal-hi"
                      : "bg-raised text-signal hover:text-signal-hi"
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
              className="h-11 min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none focus-visible:outline-none placeholder:text-ink-faint"
            />
            <button
              type="submit"
              disabled={isSending || !draft.trim()}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-signal text-bg transition-transform hover:scale-105 disabled:bg-raised disabled:text-ink-faint disabled:hover:scale-100 cursor-pointer"
              aria-label="Send"
            >
              <SendIcon />
            </button>
            </div>
            <p className="mt-2 text-center text-xs text-ink-faint">
              Answers come from your linked accounts only. Bankr can read — it can’t move money.
            </p>
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
  onOpenSource,
  isLast,
}: {
  item: StreamItem;
  token: string | null;
  onGoalCreated: () => void | Promise<void>;
  onOpenSource: (query: SourceQuery) => void;
  isLast: boolean;
}) {
  switch (item.kind) {
    case "assistant-text": {
      const breakdownQuery = item.sources?.find((s) => s.query && !s.query.merchant)?.query ?? null;
      return (
        <div className="flex items-start gap-3">
         <BotMark />
         <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
          <div className="max-w-full rounded-[6px_20px_20px_20px] bg-surface px-5 py-[18px] text-[15px] leading-[1.65] text-ink">
            <AssistantText text={item.text} />
          </div>
          {item.sources && item.sources.length > 0 && (
            <ExpandToggle
              label={`${item.sources.length} source${item.sources.length === 1 ? "" : "s"}`}
              title="Grounded in your real account data via these lookups"
            >
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                {item.sources.map((source, i) =>
                  source.query ? (
                    <button
                      key={i}
                      type="button"
                      onClick={() => onOpenSource(source.query!)}
                      title="See the transactions behind this number"
                      className="flex min-h-8 items-center gap-2 rounded-full bg-raised px-3 text-xs transition-colors hover:text-ink cursor-pointer"
                    >
                      <span className="font-mono text-signal">{i + 1}</span>
                      {source.label}
                    </button>
                  ) : (
                    <span key={i} className="flex min-h-8 items-center gap-2 rounded-full bg-raised px-3">
                      <span className="font-mono text-signal">{i + 1}</span>
                      {source.label}
                    </span>
                  ),
                )}
              </div>
              {isLast && breakdownQuery && (
                <div className="mt-2">
                  <SourceBreakdown token={token} query={breakdownQuery} onOpen={onOpenSource} />
                </div>
              )}
            </ExpandToggle>
          )}
          {item.goalProposal && (
            <GoalProposalCard
              token={token}
              proposal={item.goalProposal}
              onCreated={onGoalCreated}
            />
          )}
         </div>
        </div>
      );
    }
    case "user-text":
      return (
        <div className="flex justify-end">
          <div className="max-w-[78%] rounded-[20px_20px_6px_20px] bg-user px-[18px] py-3 text-[15px] leading-normal text-white">
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
    <div className="rounded-[20px] bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium capitalize text-ink-soft">
          {topic} · {rollup?.label ?? period}
        </h3>
        <div className="flex rounded-full bg-raised p-0.5 text-xs">
          {(["week", "month", "year"] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={`rounded-full px-2.5 py-1 capitalize transition-colors cursor-pointer ${
                period === p ? "bg-signal text-bg" : "text-ink-soft hover:text-ink"
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
                <RowAmount amount={entry.amount} group={topic} />
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

function SkeletonLine() {
  return <div className="h-4 animate-pulse rounded bg-raised" />;
}

/** Follow-ups worth asking next, from what the answer was grounded in. */
function followUpsFor(item: { sources?: ChatSource[]; goalProposal?: GoalProposal | null }): string[] {
  if (item.goalProposal) return [];
  const spending = item.sources?.find((s) => s.query);
  if (spending?.query) {
    const category = spending.query.category;
    return [
      "Compare with last month",
      category ? `Show my biggest ${category.toLowerCase()} purchases` : "What are my biggest purchases?",
      category ? `Set a ${category.toLowerCase()} budget` : "Help me set a spending budget",
    ];
  }
  if (item.sources && item.sources.length > 0) return ["What changed this month?", "Am I on pace for my goals?"];
  return [];
}

function ExpandToggle({
  label,
  title,
  children,
}: {
  label: string;
  title?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={title}
        className="flex items-center gap-1 text-xs text-ink-faint transition-colors hover:text-ink-soft cursor-pointer"
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          className={`shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {label}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

function starterPromptsFor(goals: GoalProgress[]): string[] {
  const goalName = goals[0]?.name?.trim();
  return [
    "What did I spend on food this month?",
    goalName ? `Am I on pace for ${goalName}?` : "Am I on pace for my goal?",
    "Which account grew the most this year?",
    "How steady has my income been?",
  ];
}

function SuggestionChips({ suggestions, onAsk }: { suggestions: string[]; onAsk: (text: string) => void }) {
  return (
    <div aria-label="Suggested questions" className="mb-2 flex flex-wrap gap-1.5">
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          onClick={() => onAsk(text)}
          className="cursor-pointer whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12px] leading-snug text-ink-soft transition-colors hover:border-signal hover:text-ink"
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function BotMark() {
  return (
    <div
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-raised font-mono text-[13px] font-semibold text-signal ring-[1.5px] ring-signal/60"
    >
      b_
    </div>
  );
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

function ThinkingIndicator({ label }: { label: string | null }) {
  return (
    <div className="flex items-center gap-2" role="status" aria-label={label ?? "Bankr is thinking"}>
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-signal [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-signal [animation-delay:160ms]" />
        <span className="h-1.5 w-1.5 animate-thinking rounded-full bg-signal [animation-delay:320ms]" />
      </div>
      {label && <span className="text-sm text-ink-soft">{label}</span>}
    </div>
  );
}
