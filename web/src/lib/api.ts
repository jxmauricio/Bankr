const BASE_URL = "http://localhost:8000";

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

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  // The backend anchors "this month" / "last week" to this zone, so a
  // late-evening purchase lands in the user's month, not the server's.
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (timeZone) headers["X-Timezone"] = timeZone;
  if (body !== undefined) headers["Content-Type"] = "application/json";

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

export const signUp = (email: string, password: string) =>
  request<SessionResponse>("/auth/signup", { method: "POST", body: { email, password } });

export const login = (email: string, password: string) =>
  request<SessionResponse>("/auth/login", { method: "POST", body: { email, password } });

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

// --- Goals ---

export interface GoalResponse {
  id: string;
  type: string;
  target_amount: number;
  target_date: string | null;
  starting_amount: number;
  current_progress_amount: number;
  status: string;
}

export const createGoal = (
  token: string,
  goal: { type: string; target_amount: number; target_date: string | null }
) => request<GoalResponse>("/goals", { method: "POST", token, body: goal });

export interface GoalProgress {
  id: string;
  type: string;
  target_amount: number;
  current_progress_amount: number;
  progress_fraction: number;
  target_date: string | null;
  expected_progress_fraction?: number;
  on_pace?: boolean;
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

// --- Chat ---

export interface ChatSource {
  tool: string;
  label: string;
  query?: SourceQuery | null;
}

export interface GoalProposal {
  type: string;
  target_amount: number;
  target_date: string | null;
  replaces_existing: boolean;
  at_limit?: boolean;
  active_count?: number;
  slots_remaining?: number;
}

export interface ChatResponse {
  conversation_id: string;
  reply: string;
  sources: ChatSource[];
  goal_proposal: GoalProposal | null;
}

export const sendChatMessage = (token: string, message: string, conversationId: string | null) =>
  request<ChatResponse>("/chat", {
    method: "POST",
    token,
    body: { message, conversation_id: conversationId },
  });

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
  created_at: string;
}

export const fetchConversations = (token: string) =>
  request<ConversationSummary[]>("/chat/conversations", { token });

export const fetchConversation = (token: string, conversationId: string) =>
  request<ConversationMessage[]>(`/chat/conversations/${conversationId}`, { token });
