import type { GoalProposal } from "./api";

const MONTHS: Record<string, string> = {
  january: "01",
  february: "02",
  march: "03",
  april: "04",
  may: "05",
  june: "06",
  july: "07",
  august: "08",
  september: "09",
  october: "10",
  november: "11",
  december: "12",
};

function looksLikeProgressCheck(text: string): boolean {
  return /\b(on pace|progress|how(?:'s| is| are) my goals?)\b/i.test(text);
}

export function looksLikeGoalTalk(text: string): boolean {
  if (looksLikeProgressCheck(text)) return false;
  return /\b(goal|save|saving|emergency|debt|pay\s*off|payoff|fund)\b/i.test(text);
}

export function assistantAskedToConfirm(text: string): boolean {
  return /\b(confirm(?: the)? card|hit confirm|tap (?:set )?goal|create this goal|set this as your goal)\b/i.test(
    text,
  );
}

function inferType(text: string): string {
  const lower = text.toLowerCase();
  if (/\bemergency\b/.test(lower)) return "build_emergency_fund";
  if (/\b(debt|pay\s*off|payoff|credit card|loan)\b/.test(lower)) return "pay_off_debt";
  return "save_amount";
}

function inferAmount(text: string): number | null {
  const dollar = text.match(/\$\s*([\d,]+(?:\.\d+)?)\s*(k)?/i);
  if (dollar) {
    const n = Number(dollar[1].replace(/,/g, ""));
    if (!Number.isFinite(n)) return null;
    return dollar[2] ? n * 1000 : n;
  }
  const k = text.match(/\b(\d+(?:\.\d+)?)\s*k\b/i);
  if (k) {
    const n = Number(k[1]);
    return Number.isFinite(n) ? n * 1000 : null;
  }
  for (const match of text.matchAll(/\b(\d{1,3}(?:,\d{3})+|\d{3,6})(?:\.\d+)?\b/g)) {
    const n = Number(match[1].replace(/,/g, ""));
    if (!Number.isFinite(n)) continue;
    if (n >= 1900 && n <= 2100) continue;
    if (n >= 50) return n;
  }
  return null;
}

function inferDate(text: string): string | null {
  const iso = text.match(/\b(20\d{2})-(\d{2})-(\d{2})\b/);
  if (iso) return iso[0];
  const monthYear = text.match(
    /\b(january|february|march|april|may|june|july|august|september|october|november|december)\b[^.\n]{0,20}\b(20\d{2})\b/i,
  );
  if (monthYear) {
    const month = MONTHS[monthYear[1].toLowerCase()];
    return `${monthYear[2]}-${month}-01`;
  }
  const endOfYear = text.match(/\b(?:end of|by(?: the end of)?)\s*(20\d{2})\b/i);
  if (endOfYear) return `${endOfYear[1]}-12-31`;
  return null;
}

export function inferGoalProposal(text: string): GoalProposal | null {
  if (!looksLikeGoalTalk(text) && !/\$\s*\d/.test(text)) return null;
  const amount = inferAmount(text);
  return {
    type: inferType(text),
    target_amount: amount ?? 0,
    target_date: inferDate(text),
    replaces_existing: false,
    at_limit: false,
    active_count: 0,
    slots_remaining: 5,
  };
}

export function resolveGoalProposal({
  userText,
  assistantText,
  apiProposal,
}: {
  userText: string;
  assistantText: string;
  apiProposal: GoalProposal | null | undefined;
}): GoalProposal | null {
  if (apiProposal) return apiProposal;
  if (looksLikeProgressCheck(userText)) return null;
  const inferred = inferGoalProposal(userText);
  if (inferred && (inferred.target_amount > 0 || assistantAskedToConfirm(assistantText))) {
    return inferred;
  }
  if (assistantAskedToConfirm(assistantText)) {
    return (
      inferred ?? {
        type: "save_amount",
        target_amount: 0,
        target_date: null,
        replaces_existing: false,
        at_limit: false,
        active_count: 0,
        slots_remaining: 5,
      }
    );
  }
  return null;
}
