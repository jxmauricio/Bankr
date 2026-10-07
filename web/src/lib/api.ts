// Empty string means same origin (dev shared through a tunnel, see vite.config.ts).
const BASE_URL = import.meta.env.VITE_API_BASE_URL === ""
  ? window.location.origin
  : (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000");

// FastAPI's own HTTPException(detail=...) sends a plain string, but Pydantic
// validation errors send a list of {msg, loc, ...} objects instead.
function extractErrorMessage(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d))).join(" ");
  }
  return null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function buildHeaders(token: string | null | undefined, hasJsonBody: boolean): Record<string, string> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  // The backend anchors "this month" / "last week" to this zone, so a
  // late-evening purchase lands in the user's month, not the server's.
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (timeZone) headers["X-Timezone"] = timeZone;
  if (hasJsonBody) headers["Content-Type"] = "application/json";
  return headers;
}

async function request<T>(
  path: string,
  {
    method = "GET",
    token,
    body,
    query,
  }: {
    method?: string;
    token?: string | null;
    body?: unknown;
    query?: Record<string, string>;
  } = {}
): Promise<T> {
  const url = new URL(BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  }

  const headers = buildHeaders(token, body !== undefined);

  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorMessage(body) ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// --- Auth ---

export interface SessionResponse {
  session_token: string;
}

export const signUp = (email: string, password: string, inviteCode: string) =>
  request<SessionResponse>("/auth/signup", { method: "POST", body: { email, password, invite_code: inviteCode } });

export const login = (email: string, password: string) =>
  request<SessionResponse>("/auth/login", { method: "POST", body: { email, password } });

export interface Profile {
  email: string;
}

export const fetchProfile = (token: string) => request<Profile>("/auth/me", { token });

// --- Linked accounts ---

export interface LinkTokenResponse {
  link_token: string;
}

export interface LinkAccountResponse {
  linked_account_count: number;
  transactions_synced: number;
  net_worth: number;
}

export const fetchLinkToken = (token: string) =>
  request<LinkTokenResponse>("/linked-accounts/link-token", { method: "POST", token });

export const resyncAccounts = (token: string) =>
  request<LinkAccountResponse>("/linked-accounts/sync", { method: "POST", token });

export const linkAccount = (token: string, publicToken: string) =>
  request<LinkAccountResponse>("/linked-accounts", {
    method: "POST",
    token,
    body: { public_token: publicToken },
  });

export interface LinkedBank {
  id: string;
  institution_name: string;
  status: "active" | "error";
  accounts: { name: string | null; mask: string | null; account_type: string }[];
}

export const fetchLinkedBanks = (token: string) => request<LinkedBank[]>("/linked-accounts", { token });

export const disconnectBank = (token: string, bankId: string) =>
  request<void>(`/linked-accounts/${bankId}`, { method: "DELETE", token });

export const deleteAccount = (token: string, password: string) =>
  request<void>("/auth/account", { method: "DELETE", token, body: { password } });

// --- Goals ---

export interface GoalResponse {
  id: string;
  type: string;
  name?: string | null;
  target_amount: number;
  target_date: string | null;
  starting_amount: number;
  current_progress_amount: number;
  status: string;
  category?: string | null;
  window?: string | null;
}

export const createGoal = (
  token: string,
  goal: {
    type: string;
    name?: string | null;
    target_amount: number;
    target_date?: string | null;
    category?: string | null;
    window?: string | null;
  }
) => request<GoalResponse>("/goals", { method: "POST", token, body: goal });

export const deleteGoal = (token: string, goalId: string) =>
  request<void>(`/goals/${goalId}`, { method: "DELETE", token });

export interface GoalProgress {
  id: string;
  type: string;
  name?: string | null;
  target_amount: number;
  current_progress_amount: number;
  progress_fraction: number | null;
  target_date: string | null;
  expected_progress_fraction?: number;
  on_pace?: boolean;
  category?: string | null;
  window?: string | null;
  window_label?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  label?: string | null;
  transaction_count?: number;
  over_budget?: boolean;
  remaining_amount?: number | null;
}

export interface GoalProgressResponse {
  goals: GoalProgress[];
  active_count: number;
  max_goals: number;
  message?: string;
}

export const fetchGoalProgress = (token: string) =>
  request<GoalProgressResponse>("/dashboard/goal-progress", { token });

// --- Dashboard ---

export interface AccountBalance {
  institution: string;
  name: string | null;
  mask: string | null;
  type: string;
  kind: "asset" | "liability";
  balance: number;
  reason?: string;
}

export interface NetWorthHistory {
  current: number | null;
  total_assets: number | null;
  total_liabilities: number | null;
  accounts: AccountBalance[];
  excluded_accounts: AccountBalance[];
  as_of: string | null;
  history: { date: string; net_worth: number }[];
}

export const fetchNetWorth = (token: string) => request<NetWorthHistory>("/dashboard/net-worth", { token });

export interface PeriodRollup {
  period: string;
  start: string;
  end: string;
  label: string;
  income: number;
  spending: number;
  gain: number;
  pending_spending: number;
  as_of: string | null;
}

export const fetchRollup = (token: string, period: string) =>
  request<PeriodRollup>("/dashboard/rollup", { token, query: { period } });

/** Income and spending for a named window (this_month, last_month, last_90_days, last_year, ...). */
export const fetchRollupWindow = (token: string, window: string) =>
  request<PeriodRollup>("/dashboard/rollup", { token, query: { window } });

export const fetchIncomeWindow = (token: string, window: string) =>
  request<ItemizedTransactions>("/dashboard/income", { token, query: { window } });

export const fetchSpendingWindow = (token: string, window: string) =>
  request<ItemizedTransactions>("/dashboard/spending", { token, query: { window } });

export type AverageBasis = "month" | "year";

export interface AverageCashFlow {
  basis: AverageBasis;
  income: number;
  spending: number;
  net: number;
  months_used: number;
  label: string;
  partial: boolean;
  annualized: boolean;
}

export const fetchAverage = (token: string, basis: AverageBasis, month?: string) =>
  request<AverageCashFlow>("/dashboard/average", { token, query: month ? { basis, month } : { basis } });

/** "YYYY-MM" values, newest first. */
export const fetchMonths = (token: string) => request<string[]>("/dashboard/months", { token });

export interface ItemizedItem {
  date: string;
  amount: number;
  merchant_name: string | null;
  category: string | null;
  is_pending: boolean;
}

export interface ItemizedTransactions {
  period: string | null;
  start: string;
  end: string;
  label: string;
  category: string | null;
  total: number;
  transaction_count: number;
  items: ItemizedItem[];
  as_of: string | null;
}

/** The exact filter behind a chat answer's figure (ChatSource.query). */
export interface SourceQuery {
  start: string;
  end: string;
  category: string | null;
  merchant: string | null;
}

export const fetchSpending = (token: string, period: string | SourceQuery) => {
  const query: Record<string, string> = {};
  if (typeof period === "string") query.period = period;
  else for (const [key, value] of Object.entries(period)) if (value) query[key] = value;
  return request<ItemizedTransactions>("/dashboard/spending", { token, query });
};

export const fetchIncome = (token: string, period: string) =>
  request<ItemizedTransactions>("/dashboard/income", { token, query: { period } });

export interface TransactionAccount {
  id: string;
  institution: string;
  name: string | null;
  mask: string | null;
  type: string;
}

/** One split of a transaction: same shape as a row, minus its account. */
export interface TransactionSplit {
  id: string;
  date: string;
  amount: number;
  merchant_name: string | null;
  original_merchant_name: string | null;
  category_id: string | null;
  category: string | null;
  parent_category: string | null;
  category_type: "income" | "expense" | "transfer" | null;
  is_pending: boolean;
  notes: string | null;
  is_excluded: boolean;
  is_split: boolean;
}

/** One row of the Transactions view. amount < 0 is money out. */
export interface TransactionRow extends TransactionSplit {
  splits: TransactionSplit[];
  account: TransactionAccount;
}

export interface CategoryOption {
  id: string;
  name: string;
  type: "income" | "expense" | "transfer";
}

export interface CategoryNode extends CategoryOption {
  children: CategoryOption[];
}

export const fetchCategories = (token: string) =>
  request<{ categories: CategoryNode[] }>("/categories", { token }).then((r) => r.categories);

export interface TransactionEdit {
  category_id?: string;
  /** "" restores the bank's name. */
  merchant_name?: string;
  /** "" clears the note. */
  notes?: string;
  excluded?: boolean;
}

/** Returns the edited row without its account (the caller keeps that). */
export const updateTransaction = (token: string, id: string, edit: TransactionEdit) =>
  request<Omit<TransactionRow, "account">>(`/transactions/${id}`, { method: "PATCH", token, body: edit });

/** amounts use the transaction's sign and must sum to it; [] removes the split. */
export const setTransactionSplits = (
  token: string,
  id: string,
  splits: { amount: number; category_id: string; note?: string }[],
) => request<Omit<TransactionRow, "account">>(`/transactions/${id}/splits`, { method: "PUT", token, body: { splits } });

export interface TransactionList {
  window: string;
  start: string;
  end: string;
  label: string;
  transaction_count: number;
  truncated: boolean;
  transactions: TransactionRow[];
  as_of: string | null;
}

export const fetchTransactions = (token: string, window: string) =>
  request<TransactionList>("/dashboard/transactions", { token, query: { window } });

export interface Rule {
  id: string;
  merchant_contains: string;
  amount_min: number | null;
  amount_max: number | null;
  linked_account_id: string | null;
  set_category_id: string;
  set_category: string | null;
  set_merchant_name: string | null;
  priority: number;
  created_at: string | null;
  /** Only on create with apply_to_existing. */
  applied_to?: number;
}

export interface NewRule {
  merchant_contains: string;
  set_category_id: string;
  set_merchant_name?: string;
  amount_min?: number;
  amount_max?: number;
  apply_to_existing?: boolean;
}

export const fetchRules = (token: string) => request<{ rules: Rule[] }>("/rules", { token }).then((r) => r.rules);

export const previewRule = (token: string, merchant: string, categoryId: string) =>
  request<{ would_change: number }>("/rules/preview", {
    token,
    query: { merchant_contains: merchant, category_id: categoryId },
  }).then((r) => r.would_change);

export const createRule = (token: string, rule: NewRule) => request<Rule>("/rules", { method: "POST", token, body: rule });

export const updateRule = (token: string, id: string, patch: Partial<NewRule>) =>
  request<Rule>(`/rules/${id}`, { method: "PATCH", token, body: patch });

export const deleteRule = (token: string, id: string) => request<void>(`/rules/${id}`, { method: "DELETE", token });

export type RecurringKind = "bill" | "subscription" | "income";
export type RecurringStatus = "suggested" | "confirmed" | "dismissed";

export interface RecurringSeries {
  id: string;
  name: string;
  kind: RecurringKind;
  cadence: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
  status: RecurringStatus;
  category_id: string | null;
  typical_amount: number;
  last_amount: number;
  last_date: string;
  next_expected_date: string;
  monthly_amount: number;
  occurrences: number;
  is_active: boolean;
  price_changed: boolean;
}

export interface UpcomingCharge {
  series_id: string;
  name: string;
  kind: RecurringKind;
  status: RecurringStatus;
  date: string;
  amount: number;
}

export interface RecurringOverview {
  today: string;
  series: RecurringSeries[];
  upcoming: UpcomingCharge[];
  /** Confirmed series only, as a monthly amount. */
  monthly: { subscriptions: number; bills: number; income: number };
  suggested_count: number;
}

export const fetchRecurring = (token: string) => request<RecurringOverview>("/recurring", { token });

export const updateRecurring = (token: string, id: string, patch: { status?: RecurringStatus; kind?: RecurringKind; name?: string }) =>
  request<RecurringSeries>(`/recurring/${id}`, { method: "PATCH", token, body: patch });

export type BudgetLineStatus = "ok" | "warning" | "over";

export interface BudgetLine {
  /** Category id, or "flex" for the Flexible bucket. */
  key: string;
  category_id: string | null;
  name: string;
  group: "fixed" | "flex" | "category";
  budgeted: number;
  carryover: number;
  moved: number;
  spent: number;
  available: number;
  rollover: boolean;
  projected_spent: number | null;
  status: BudgetLineStatus;
}

export interface BudgetCategorySpend {
  category_id: string;
  name: string;
  spent: number;
}

export interface BudgetStatus {
  month: string;
  label: string;
  start: string;
  end: string;
  today: string;
  elapsed_fraction: number;
  mode: "flex" | "category";
  has_budget: boolean;
  lines: BudgetLine[];
  flex: (BudgetLine & { categories: BudgetCategorySpend[] }) | null;
  unbudgeted: BudgetCategorySpend[];
  income: { so_far: number; last_month: number };
  totals: { budgeted: number; spent: number; available: number };
}

export interface BudgetSuggestionLine {
  category_id: string;
  name: string;
  amount: number;
  group: "fixed" | "flex";
  typical_spent: number;
}

export interface BudgetSuggestion {
  months: string[];
  mode: "flex";
  flex_amount: number;
  lines: BudgetSuggestionLine[];
}

export const fetchBudget = (token: string, month?: string) =>
  request<BudgetStatus>("/budgets", { token, query: month ? { month } : undefined });

export const fetchBudgetSuggestion = (token: string) => request<BudgetSuggestion>("/budgets/suggestion", { token });

export const setupBudget = (
  token: string,
  body: { mode: "flex" | "category"; flex_amount: number; lines: { category_id: string; amount: number; group: "fixed" | "flex" }[] },
) => request<BudgetStatus>("/budgets/setup", { method: "POST", token, body });

export const updateBudgetSettings = (
  token: string,
  patch: { mode?: "flex" | "category"; flex_amount?: number; flex_rollover?: boolean },
) => request<BudgetStatus>("/budgets/settings", { method: "PUT", token, body: patch });

export const upsertBudget = (
  token: string,
  categoryId: string,
  patch: { amount?: number; group?: "fixed" | "flex"; rollover?: boolean },
) => request<BudgetStatus>(`/budgets/${categoryId}`, { method: "PUT", token, body: patch });

export const deleteBudget = (token: string, categoryId: string) =>
  request<BudgetStatus>(`/budgets/${categoryId}`, { method: "DELETE", token });

export const moveBudgetMoney = (token: string, move: { month?: string; from_key: string; to_key: string; amount: number }) =>
  request<BudgetStatus>("/budgets/moves", { method: "POST", token, body: move });

export interface CashFlowBreakdown {
  window: string;
  start: string;
  end: string;
  label: string;
  income: number;
  spending: number;
  net: number;
  sources: { name: string; amount: number }[];
  categories: { name: string; amount: number }[];
  as_of: string | null;
}

export const fetchCashFlow = (token: string, window: string) =>
  request<CashFlowBreakdown>("/dashboard/cash-flow", { token, query: { window } });

export interface SpendingPaceMonth {
  start: string;
  days_in_month: number;
  /** Running total, one entry per day from the 1st. */
  running: number[];
  label: string;
}

export interface SpendingPace {
  today: string;
  this_month: SpendingPaceMonth;
  last_month: SpendingPaceMonth;
}

export const fetchSpendingPace = (token: string) => request<SpendingPace>("/dashboard/spending-pace", { token });

// --- Chat ---

export interface ChatSource {
  tool: string;
  label: string;
  query?: SourceQuery | null;
}

export interface GoalProposal {
  type: string;
  name?: string | null;
  target_amount: number;
  target_date: string | null;
  category?: string | null;
  window?: string | null;
  replaces_existing: boolean;
  at_limit?: boolean;
  active_count?: number;
  slots_remaining?: number;
}

export interface ChartPoint {
  label: string;
  value: number;
  share?: number | null;
  partial?: boolean;
}

/** A small chart under a reply, built server-side from a fresh query. */
export interface ChartSpec {
  kind: "breakdown" | "compare" | "trend";
  title: string;
  period?: string | null;
  unit: "usd";
  points: ChartPoint[];
  change?: { difference: number; percent_change: number | null; direction: "up" | "down" | "flat" } | null;
}

export interface RuleProposal {
  kind: "rule";
  merchant_contains: string;
  category_id: string;
  category: string;
  set_merchant_name: string | null;
  would_change: number;
}

export interface BudgetMoveProposal {
  kind: "budget_move";
  month: string;
  from_key: string;
  from_name: string;
  to_key: string;
  to_name: string;
  amount: number;
}

/** A confirm card the assistant drafted; nothing is changed until the user confirms. */
export type ActionProposal = RuleProposal | BudgetMoveProposal;

export interface ChatResponse {
  conversation_id: string;
  reply: string;
  sources: ChatSource[];
  goal_proposal: GoalProposal | null;
  action_proposal?: ActionProposal | null;
  charts?: ChartSpec[];
}

/**
 * Sends a chat turn over Server-Sent Events (POST /chat/stream): onStatus
 * fires with a progress line ("Looking up Dining spending…") before each tool
 * runs, and the promise resolves with the final reply. A stream that ends
 * without a reply rejects with an ApiError like any other failure.
 */
export async function streamChatMessage(
  token: string,
  message: string,
  conversationId: string | null,
  onStatus: (label: string) => void
): Promise<ChatResponse> {
  const response = await fetch(new URL(BASE_URL + "/chat/stream"), {
    method: "POST",
    headers: buildHeaders(token, true),
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorMessage(body) ?? `Request failed (${response.status})`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    // Events are separated by a blank line; keep any partial tail for the next chunk.
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = block.match(/^event: (.*)$/m)?.[1];
      const data = block.match(/^data: (.*)$/m)?.[1];
      if (!event || data === undefined) continue; // keepalive comment
      const payload = JSON.parse(data);
      if (event === "status") onStatus(payload.label);
      else if (event === "done") return payload as ChatResponse;
      else if (event === "error") throw new ApiError(500, payload.message);
    }
  }
  throw new ApiError(500, "Bankr couldn't respond. Try again.");
}

export interface ConversationSummary {
  conversation_id: string;
  preview: string;
  last_message_at: string;
  message_count: number;
}

export interface ConversationMessage {
  role: string;
  content: string;
  sources: ChatSource[];
  goal_proposal: GoalProposal | null;
  action_proposal?: ActionProposal | null;
  charts?: ChartSpec[];
  created_at: string;
}

export const fetchConversations = (token: string) =>
  request<ConversationSummary[]>("/chat/conversations", { token });

export const fetchConversation = (token: string, conversationId: string) =>
  request<ConversationMessage[]>(`/chat/conversations/${conversationId}`, { token });
