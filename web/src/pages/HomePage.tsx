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
  type ChartSpec,
  type ChatSource,
  type GoalProgress,
  type GoalProposal,
  type LinkedBank,
  type ItemizedTransactions,
  type PeriodRollup,
  type SourceQuery,
} from "../lib/api";
import { resolveGoalProposal } from "../lib/goalProposal";
import { GoalsSection } from "../components/GoalsSection";
import { GoalProposalCard } from "../components/GoalProposalCard";
import { CreateGoalModal } from "../components/CreateGoalModal";
import { isOAuthReturn } from "../lib/plaidOAuth";
import { MoneyCard, MoneyPill, type MoneySummary } from "../components/MoneyRail";
import { useCashFlow } from "../lib/useCashFlow";
import { ProfileMenu } from "../components/ProfileMenu";
import { PeriodFilter } from "../components/PeriodFilter";
import { loadPeriod, savePeriod, type Period as TimePeriod } from "../lib/period";
import { RelinkBanner } from "../components/StatusBanners";
import { ChatChart } from "../components/ChatChart";
import { SourceBreakdown } from "../components/SourceBreakdown";
import { SettingsModal } from "../components/SettingsModal";
import { NetWorthFlowModal } from "../components/NetWorthFlowModal";
import { TransactionSearchModal } from "../components/TransactionSearchModal";
import { ChatHistoryMenu } from "../components/ChatHistoryMenu";
import { useSession } from "../lib/session";
import { useVoiceMode, type VoiceState } from "../lib/useVoiceMode";
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
  | { kind: "assistant-text"; id: string; text: string; sources?: ChatSource[]; goalProposal?: GoalProposal | null; charts?: ChartSpec[] }
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
  // Seeded from localStorage (not null) so the sync effect below doesn't wipe
  // the saved id on mount before the restore effect gets to read it.
  const [conversationId, setConversationId] = useState<string | null>(() => localStorage.getItem(LAST_CONVERSATION_KEY));
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The question whose answer failed, so it can be retried or edited in place.
  const [failed, setFailed] = useState<{ itemId: string; text: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [showFlow, setShowFlow] = useState(false);
  const [sourceQuery, setSourceQuery] = useState<SourceQuery | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  // Phones: the money rail collapses into the top bar and drops down on tap.
  const [moneyOpen, setMoneyOpen] = useState(false);
  const flow = useCashFlow(token, period, monthRollup);
  const streamRef = useRef<HTMLDivElement>(null);
  const voice = useVoiceMode({
    onFinalTranscript: (text) => ask(text),
    onDraftChange: setDraft,
    onError: setError,
  });
  const { voiceMode, voiceState, toggle: toggleVoiceMode, speakReply } = voice;

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
    if (!moneyOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMoneyOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [moneyOpen]);

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
    const itemId = makeId();
    pushItem({ kind: "user-text", id: itemId, text });
    setError(null);
    setFailed(null);
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
        charts: response.charts,
        goalProposal: resolveGoalProposal({
          userText: text,
          assistantText: response.reply,
          apiProposal: response.goal_proposal,
        }),
      });
      speakReply(response.reply);
    } catch {
      setFailed({ itemId, text });
    } finally {
      setIsSending(false);
      setStatusLabel(null);
    }
  }

  /** Drop the failed question from the stream, then re-ask it or hand it back to the composer. */
  function resolveFailed(action: "retry" | "edit") {
    if (!failed) return;
    setItems((prev) => prev.filter((i) => i.id !== failed.itemId));
    setFailed(null);
    if (action === "retry") {
      ask(failed.text);
    } else {
      setDraft(failed.text);
      inputRef.current?.focus();
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
    setFailed(null);
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
            charts: m.charts,
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
      if (silent) setConversationId(null);
      if (!silent) setError(err instanceof ApiError ? err.message : "Couldn't load that conversation.");
    }
  }

  // Restore the conversation that was active last time, if any, so a
  // refresh (or reopening the tab) lands back where the user left off.
  useEffect(() => {
    if (!token) return;
    if (conversationId) loadConversation(conversationId, { silent: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function startNewChat() {
    setError(null);
    setFailed(null);
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

  const summary: MoneySummary = {
    netWorth,
    flow,
    history: nwHistory,
    asOf: nwAsOf ?? monthRollup?.as_of,
    accountCount,
    excludedCount,
    bankCount: banks.length,
    isRefreshing,
    showStale: brokenBanks.length === 0,
  };
  const goalsSection = (
    <GoalsSection
      goals={goals}
      token={token}
      onGoalDeleted={refreshGoalProgress}
      onCreateGoal={() => {
        setMoneyOpen(false);
        setCreatingGoal(true);
      }}
      onSuggestGoal={() => {
        setMoneyOpen(false);
        ask("Help me set a goal");
      }}
    />
  );
  const openFlow = () => {
    setMoneyOpen(false);
    setShowFlow(true);
  };

  return (
    <div className="relative flex h-dvh flex-col">
      <header className="relative z-30 flex min-h-16 shrink-0 items-center justify-between gap-1 border-b border-line bg-bg px-1.5 py-2 sm:gap-2 sm:px-6">
        <div className="flex shrink-0 items-center gap-3">
          <ChatHistoryMenu token={token} onSelectConversation={loadConversation} onNewChat={startNewChat} />
          <span className="hidden font-display text-[21px] font-semibold tracking-tight text-ink sm:inline">
            bankr<span className="text-signal">_</span>
          </span>
          <span className="hidden rounded-full bg-signal-wash px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] text-signal md:inline">PRIVATE BETA</span>
        </div>
        <div className="flex min-w-0 max-w-[420px] flex-1 lg:hidden">
          <MoneyPill summary={summary} open={moneyOpen} onToggle={() => setMoneyOpen((o) => !o)} />
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="hidden lg:block">
            <PeriodFilter period={period} onChange={changePeriod} />
          </div>
          {token && (
            <ProfileMenu
              token={token}
              onOpenSettings={() => setShowSettings(true)}
              onSignOut={signOut}
              attention={brokenBanks.length > 0}
            />
          )}
        </div>
        {moneyOpen && (
          <div className="lg:hidden">
            <button
              type="button"
              aria-label="Close your money"
              onClick={() => setMoneyOpen(false)}
              className="fixed inset-0 -z-10 cursor-default bg-[rgb(5_6_8/0.72)]"
            />
            <section
              id="money-sheet"
              role="dialog"
              aria-label="Your money"
              className="absolute inset-x-0 top-full mx-auto flex max-h-[calc(100dvh-96px)] animate-drop max-w-[560px] flex-col gap-3 overflow-y-auto rounded-b-3xl border-b border-line-strong bg-bg px-4 pb-4 pt-3 shadow-modal"
            >
              <div className="flex justify-end">
                <PeriodFilter period={period} onChange={changePeriod} />
              </div>
              <MoneyCard summary={summary} onNetWorthClick={openFlow} onRefresh={refreshFromBank} />
              {goalsSection}
              <button
                type="button"
                onClick={() => setMoneyOpen(false)}
                className="h-11 shrink-0 cursor-pointer rounded-[14px] bg-raised text-sm text-ink"
              >
                Back to chat
              </button>
            </section>
          </div>
        )}
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

      <div className="flex min-h-0 flex-1">
        {/* Desktop money rail: its own column, scrolling apart from the chat. */}
        <aside
          aria-label="Your money"
          className="hidden w-[320px] shrink-0 flex-col gap-3.5 overflow-y-auto border-r border-line p-5 lg:flex"
        >
          <MoneyCard summary={summary} onNetWorthClick={openFlow} onRefresh={refreshFromBank} />
          {goalsSection}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div
            ref={streamRef}
            className="flex-1 overflow-y-auto px-4 py-3 [mask-image:linear-gradient(to_bottom,transparent_0,#000_28px)] sm:px-7"
          >
            <div className="mx-auto flex max-w-2xl flex-col gap-4 pt-2">
              {brokenBanks.length > 0 && <RelinkBanner banks={brokenBanks} onManage={() => setShowSettings(true)} />}
              {isGreeting && <FirstConversation accountCount={accountCount} />}
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
              {failed && !isSending && (
                <AnswerFailed onRetry={() => resolveFailed("retry")} onEdit={() => resolveFailed("edit")} />
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
            className="mx-auto w-full max-w-2xl shrink-0 px-3 pb-[max(20px,env(safe-area-inset-bottom))] pt-2 sm:px-7"
          >
            {!voiceMode && composerSuggestions.length > 0 && (
              <SuggestionChips suggestions={composerSuggestions} onAsk={ask} />
            )}
            {voiceMode ? (
              <VoicePanel
                state={voiceState}
                transcript={draft}
                isWaiting={isSending}
                onTalk={voice.talk}
                onPause={voice.pause}
                onInterrupt={toggleVoiceMode}
                onExit={voice.stop}
              />
            ) : (
              <div className="flex items-center gap-2 rounded-3xl border border-control bg-surface p-1.5 focus-within:border-signal">
                <button
                  type="button"
                  onClick={toggleVoiceMode}
                  aria-label="Start voice mode"
                  className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-raised text-signal transition-colors hover:text-signal-hi"
                >
                  <MicIcon />
                </button>
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Ask about your money"
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
            )}
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
          {item.charts?.map((chart, i) => <ChatChart key={i} chart={chart} />)}
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

function BotMark({ failed = false }: { failed?: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-raised font-mono text-[13px] font-semibold ring-[1.5px] ${
        failed ? "text-negative ring-negative/60" : "text-signal ring-signal/60"
      }`}
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

function greetingForNow(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 18) return "Good afternoon.";
  return "Good evening.";
}

/** Fills the empty stream before the first question: who Bankr is and how to check its answers. */
function FirstConversation({ accountCount }: { accountCount?: number }) {
  const accounts = accountCount ? `your ${accountCount} linked account${accountCount === 1 ? "" : "s"}` : "your linked accounts";
  return (
    <section className="flex flex-col gap-6 pb-2 pt-6 sm:gap-7 sm:pt-10">
      <div
        aria-hidden="true"
        className="flex h-11 w-11 items-center justify-center rounded-[10px] border border-signal font-mono text-[22px] font-semibold text-signal"
      >
        b_
      </div>
      <div className="flex flex-col gap-2.5">
        <h1 className="font-display text-[30px] font-normal leading-[1.12] tracking-[-0.015em] text-ink sm:text-[40px]">
          {greetingForNow()} What would you like to know?
        </h1>
        <p className="max-w-[520px] text-[15px] leading-relaxed text-ink-soft">
          I’ve read {accounts}. Ask in plain words — I’ll answer with the numbers and show you where they came from.
        </p>
      </div>
      <div className="flex items-start gap-3.5 rounded-xl border border-dashed border-line-strong p-4">
        <svg className="mt-0.5 shrink-0" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-signal)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6l-7-3Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
        <div className="flex flex-col gap-1.5 text-[13px] leading-normal text-ink-soft">
          <span className="font-medium text-ink">How to check any answer</span>
          <span>
            Figures with a dotted underline, like <span className="fig text-ink">$612.40</span>, are sourced. Open the
            sources under the answer to see every transaction behind them.
          </span>
        </div>
      </div>
    </section>
  );
}

/** A failed answer reads calm, never guesses a number, and offers one way forward. */
function AnswerFailed({ onRetry, onEdit }: { onRetry: () => void; onEdit: () => void }) {
  return (
    <div className="flex items-start gap-3">
      <BotMark failed />
      <div role="alert" className="flex flex-1 flex-col gap-3 rounded-[6px_20px_20px_20px] bg-surface px-[18px] py-4">
        <p className="text-[15px] leading-relaxed text-ink">
          I couldn’t reach your transaction data just now, so I won’t guess. Nothing in your accounts was changed.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="h-11 cursor-pointer rounded-[14px] bg-raised px-[18px] text-sm font-medium text-ink hover:text-signal-hi"
          >
            ↻ Try again
          </button>
          <button
            type="button"
            onClick={onEdit}
            className="h-11 cursor-pointer rounded-[14px] px-3.5 text-sm text-ink-soft hover:text-ink"
          >
            Edit question
          </button>
        </div>
      </div>
    </div>
  );
}

/** Voice mode takes over the composer's slot: idle, listening (you), speaking (Bankr). */
function VoicePanel({
  state,
  transcript,
  isWaiting,
  onTalk,
  onPause,
  onInterrupt,
  onExit,
}: {
  state: VoiceState;
  transcript: string;
  isWaiting: boolean;
  onTalk: () => void;
  onPause: () => void;
  onInterrupt: () => void;
  onExit: () => void;
}) {
  const listening = state === "listening";
  const speaking = state === "speaking";
  const status = listening ? "Listening" : speaking ? "Speaking" : isWaiting ? "Thinking" : "Voice";
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center gap-4 rounded-3xl border bg-surface px-5 pb-5 pt-3 ${
        listening ? "border-ink/35" : speaking ? "border-signal/50" : "border-line"
      }`}
    >
      <div className="flex w-full items-center justify-between">
        <span
          className={`flex items-center gap-2 text-[13px] ${
            listening ? "text-ink" : speaking ? "text-signal" : "text-ink-soft"
          }`}
        >
          {(listening || speaking) && (
            <span className={`h-2 w-2 rounded-full ${listening ? "bg-ink" : "bg-signal"}`} />
          )}
          {status}
        </span>
        <button
          type="button"
          onClick={onExit}
          aria-label="Exit voice mode"
          className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-[10px] text-ink-soft hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      {listening ? (
        <div className="relative h-16 w-16">
          <span className="absolute inset-0 animate-ring rounded-full border-2 border-ink" />
          <button
            type="button"
            onClick={onPause}
            aria-label="Stop listening"
            className="absolute inset-0 flex cursor-pointer items-center justify-center rounded-full bg-user"
          >
            <span className="h-4 w-4 rounded-[3px] bg-white" />
          </button>
        </div>
      ) : speaking ? (
        <div aria-hidden className="flex h-16 w-16 items-center justify-center gap-1 rounded-[10px] border border-signal">
          <LevelBars count={4} className="bg-signal" />
        </div>
      ) : (
        <button
          type="button"
          onClick={onTalk}
          disabled={isWaiting}
          aria-label="Start talking"
          className="flex h-16 w-16 cursor-pointer items-center justify-center rounded-[10px] border border-signal bg-raised text-signal hover:text-signal-hi disabled:cursor-default disabled:border-line-strong disabled:text-ink-faint"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden>
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        </button>
      )}

      {listening ? (
        <>
          <div aria-hidden className="flex h-6 items-center gap-1">
            <LevelBars count={5} className="bg-ink" />
          </div>
          {transcript && (
            <p className="text-center font-display text-lg leading-snug text-ink">“{transcript}”</p>
          )}
          <span className="text-xs text-ink-faint">Pause to send · tap the square to stop</span>
        </>
      ) : speaking ? (
        <button
          type="button"
          onClick={onInterrupt}
          className="h-11 cursor-pointer rounded-full border border-line-strong px-[18px] text-[13px] text-ink hover:border-signal"
        >
          Tap to interrupt
        </button>
      ) : (
        <>
          <div className="flex flex-col items-center gap-1 text-center">
            <span className="font-display text-lg text-ink">{isWaiting ? "Working on it…" : "Tap to talk"}</span>
            <span className="text-[13px] leading-normal text-ink-soft">
              Try “How much is in savings?” Answers also appear in the chat with sources.
            </span>
          </div>
          <button
            type="button"
            onClick={onExit}
            className="h-11 cursor-pointer rounded-[10px] border border-line-strong px-4 text-[13px] text-ink-soft hover:text-ink"
          >
            Switch to typing
          </button>
        </>
      )}
    </div>
  );
}

const LEVEL_HEIGHTS = [14, 26, 32, 20, 12];

function LevelBars({ count, className }: { count: number; className: string }) {
  return LEVEL_HEIGHTS.slice(0, count).map((height, i) => (
    <span
      key={i}
      className={`w-1 animate-level rounded-sm ${className}`}
      style={{ height: Math.min(height, 28), animationDelay: `${i * 0.12}s` }}
    />
  ));
}
