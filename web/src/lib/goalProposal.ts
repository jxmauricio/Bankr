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

const CATEGORY_HINTS: [RegExp, string][] = [
  [/\b(eating out|eat out|dine|dining|restaurants?|takeout|take-out|food delivery)\b/i, "Dining"],
  [/\b(fast food|drive[- ]?thru)\b/i, "Fast Food"],
  [/\b(coffee|cafe|cafes|starbucks)\b/i, "Coffee"],
  [/\b(bars?|drinks|alcohol|nightlife)\b/i, "Alcohol & Bars"],
  [/\b(grocer(?:y|ies)|supermarket|trader joe)\b/i, "Groceries"],
  [/\b(gas|fuel|petrol)\b/i, "Gas"],
  [/\b(uber|lyft|rideshare|taxi)\b/i, "Rideshare & Taxi"],
  [/\b(transit|subway|bus|train)\b/i, "Public Transit"],
  [/\b(parking|tolls?)\b/i, "Parking & Tolls"],
  [/\b(travel|flights?|hotels?|vacation|trips?)\b/i, "Travel"],
  [/\b(rent|housing)\b/i, "Rent & Housing"],
  [/\b(utilities|electric|internet|phone bill)\b/i, "Utilities"],
  [/\b(subscriptions?|streaming|netflix)\b/i, "Subscriptions"],
  [/\b(entertainment|movies?|fun)\b/i, "Entertainment"],
  [/\b(shopping|amazon|clothes)\b/i, "Shopping"],
  [/\b(health|doctor|pharmacy|gym)\b/i, "Health"],
  [/\b(transport|commute|driving)\b/i, "Transportation"],
];

function looksLikeProgressCheck(text: string): boolean {
  return /\b(on pace|progress|how(?:'s| is| are) my goals?)\b/i.test(text);
}

function looksLikeSpendingQuestion(text: string): boolean {
  return /\bhow much (?:did|have|was|were|am i)\b/i.test(text) || /\bwhat did i spend\b/i.test(text);
}

const TRACK_INTENT =
  /\b(track|tracking|keep (?:an |a )?eye on|watch(?:ing)? (?:my )?|too much|overspend|budget (?:for|on)|set a budget|limit (?:my|on)|cap (?:my|on))\b/i;

export function looksLikeSpendingTrack(text: string): boolean {
  if (looksLikeProgressCheck(text)) return false;
  if (looksLikeSpendingQuestion(text) && !TRACK_INTENT.test(text)) return false;
  return TRACK_INTENT.test(text);
}

export function looksLikeGoalTalk(text: string): boolean {
  if (looksLikeProgressCheck(text)) return false;
  if (looksLikeSpendingTrack(text)) return true;
  return /\b(goal|save|saving|emergency|debt|pay\s*off|payoff|fund)\b/i.test(text);
}

export function assistantAskedToConfirm(text: string): boolean {
  return /\b(confirm(?: the)? card|hit confirm|tap (?:set )?goal|create this goal|set this as your goal|start tracking|track this)\b/i.test(
    text,
  );
}

function inferType(text: string): string {
  if (looksLikeSpendingTrack(text)) return "track_spending";
  return "save";
}

function inferName(text: string): string | null {
  if (looksLikeSpendingTrack(text)) return inferCategory(text);
  const lower = text.toLowerCase();
  if (/\bemergency\b/.test(lower)) return "Emergency fund";
  if (/\b(debt|pay\s*off|payoff|credit card|loan)\b/.test(lower)) return "Paying off debt";
  const forThing = text.match(
    /\b(?:save|saving|savings)\s+(?:up\s+)?(?:for|towards?)\s+(?:a |an |the )?([a-z][a-z\s'-]{1,40})/i,
  );
  if (forThing) {
    const thing = forThing[1].trim().replace(/\s+(by|in|before|this|next).*$/i, "");
    if (thing) return thing.charAt(0).toUpperCase() + thing.slice(1);
  }
  return "Savings";
}

function inferCategory(text: string): string | null {
  for (const [pattern, name] of CATEGORY_HINTS) {
    if (pattern.test(text)) return name;
  }
  return null;
}

function inferWindow(text: string): string {
  const lower = text.toLowerCase();
  if (/\bthis week\b/.test(lower) || /\bweekly\b/.test(lower)) return "this_week";
  if (/\bthis year\b/.test(lower) || /\byearly\b/.test(lower)) return "this_year";
  if (/\blast 7 days\b|\bpast week\b/.test(lower)) return "last_7_days";
  if (/\blast 30 days\b|\bpast month\b/.test(lower)) return "last_30_days";
  if (/\blast 90 days\b|\bpast (?:three|3) months\b/.test(lower)) return "last_90_days";
  return "this_month";
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

function emptyMeta(): Pick<GoalProposal, "replaces_existing" | "at_limit" | "active_count" | "slots_remaining"> {
  return {
    replaces_existing: false,
    at_limit: false,
    active_count: 0,
    slots_remaining: 5,
  };
}

export function inferGoalProposal(text: string): GoalProposal | null {
  if (looksLikeSpendingTrack(text)) {
    return {
      type: "track_spending",
      name: inferName(text),
      target_amount: inferAmount(text) ?? 0,
      target_date: null,
      category: inferCategory(text),
      window: inferWindow(text),
      ...emptyMeta(),
    };
  }
  if (!looksLikeGoalTalk(text) && !/\$\s*\d/.test(text)) return null;
  const amount = inferAmount(text);
  return {
    type: inferType(text),
    name: inferName(text),
    target_amount: amount ?? 0,
    target_date: inferDate(text),
    category: null,
    window: null,
    ...emptyMeta(),
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
  if (inferred && inferred.type === "track_spending") {
    if (inferred.category || assistantAskedToConfirm(assistantText) || looksLikeSpendingTrack(userText)) {
      return inferred;
    }
  }
  if (inferred && inferred.type !== "track_spending" && (inferred.target_amount > 0 || assistantAskedToConfirm(assistantText))) {
    return inferred;
  }
  if (assistantAskedToConfirm(assistantText)) {
    return (
      inferred ?? {
        type: "save",
        name: "Savings",
        target_amount: 0,
        target_date: null,
        category: null,
        window: null,
        ...emptyMeta(),
      }
    );
  }
  return null;
}
