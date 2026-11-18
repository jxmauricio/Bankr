import type { OnboardingLifestyle, OnboardingOccupation } from "@/lib/api";

export type DraftDebt = { name: string; owed: string; paid_off: string };
export type DraftInvestment = { name: string; amount: string };
export type DraftGoal = { name: string; target: string; saved: string };
export type HousingKind = "rent" | "mortgage" | "none";

const SAVE_RATE: Record<OnboardingLifestyle, number> = {
  strict: 0.45,
  balanced: 0.2,
  ball: 0.08,
};

/** Share of leftover living money: groceries, dining, common costs. */
const LIVE_SPLIT: Record<OnboardingLifestyle, [number, number, number]> = {
  strict: [0.5, 0.1, 0.4],
  balanced: [0.4, 0.25, 0.35],
  ball: [0.28, 0.42, 0.3],
};

export function parseMoney(raw: string): number {
  return Number(String(raw).replace(/[$,\s]/g, ""));
}

export function dollars(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
}

function sum(values: number[]): number {
  return values.reduce((a, b) => a + b, 0);
}

function moneyOrZero(raw: string): number {
  const n = parseMoney(raw);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export type BudgetLine = { name: string; amount: number; colorKey: string };

export function roughBudget(
  income: number,
  lifestyle: OnboardingLifestyle,
  debts: DraftDebt[],
  housingKind: HousingKind | null,
  housingPayment: number
): {
  income: number;
  housing: number;
  housingLabel: string;
  debt: number;
  save: number;
  live: number;
  budgeted: number;
  left: number;
  lines: BudgetLine[];
} {
  const housing = housingKind && housingKind !== "none" ? Math.max(0, Math.round(housingPayment)) : 0;
  const housingLabel = housingKind === "mortgage" ? "Mortgage" : "Rent";
  const owed = sum(debts.map((d) => moneyOrZero(d.owed)));
  const afterHousing = income - housing;
  const debt = owed > 0 ? Math.round(Math.min(Math.max(afterHousing, 0) * 0.2, owed / 24)) : 0;
  const afterFixed = afterHousing - debt;
  const save = afterFixed > 0 ? Math.round(afterFixed * SAVE_RATE[lifestyle]) : 0;
  const live = Math.max(0, afterFixed - save);
  const [gShare, dShare, cShare] = LIVE_SPLIT[lifestyle];
  const groceries = Math.round(live * gShare);
  const dining = Math.round(live * dShare);
  const common = Math.max(0, live - groceries - dining);
  const budgeted = housing + debt + live;
  const left = income - budgeted;
  const lines: BudgetLine[] = [];
  if (housing > 0) lines.push({ name: housingLabel, amount: housing, colorKey: housingKind === "mortgage" ? "Mortgage" : "Rent" });
  if (debt > 0) lines.push({ name: "Debt", amount: debt, colorKey: "Loan Payment" });
  if (groceries > 0) lines.push({ name: "Groceries", amount: groceries, colorKey: "Groceries" });
  if (dining > 0) lines.push({ name: "Dining", amount: dining, colorKey: "Restaurants & Bars" });
  if (common > 0) lines.push({ name: "Common costs", amount: common, colorKey: "Bills & Utilities" });
  return { income, housing, housingLabel, debt, save, live, budgeted, left, lines: lines.slice(0, 5) };
}

export function suggestedGoals(
  goals: DraftGoal[],
  debts: DraftDebt[],
  income: number,
  emergency: { saved: number; target: number }
): { name: string; target: number; saved: number }[] {
  const out: { name: string; target: number; saved: number }[] = [];
  const seen = new Set<string>();

  function add(name: string, target: number, saved = 0) {
    const key = name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ name, target, saved: Math.max(0, saved) });
  }

  const eTarget = emergency.target > 0 ? emergency.target : income > 0 ? income * 3 : 0;
  add("Emergency fund", eTarget, emergency.saved);

  for (const g of goals) {
    if (/emergency/i.test(g.name)) continue;
    add(g.name, moneyOrZero(g.target), moneyOrZero(g.saved));
  }

  const biggest = [...debts].sort((a, b) => moneyOrZero(b.owed) - moneyOrZero(a.owed))[0];
  if (biggest && moneyOrZero(biggest.owed) > 0 && !out.some((g) => /debt|pay off/i.test(g.name))) {
    add(`Pay off ${biggest.name}`, moneyOrZero(biggest.owed) + moneyOrZero(biggest.paid_off), moneyOrZero(biggest.paid_off));
  }
  return out.slice(0, 3);
}

export function estimatedNetWorth(
  investments: DraftInvestment[],
  debts: DraftDebt[],
  cash: number,
  emergency = 0
): { assets: number; cash: number; emergency: number; invested: number; owed: number; net: number } {
  const invested = sum(investments.map((i) => moneyOrZero(i.amount)));
  const liquid = Number.isFinite(cash) && cash > 0 ? cash : 0;
  const fund = Number.isFinite(emergency) && emergency > 0 ? emergency : 0;
  const owed = sum(debts.map((d) => moneyOrZero(d.owed)));
  const assets = invested + liquid + fund;
  return { assets, cash: liquid, emergency: fund, invested, owed, net: assets - owed };
}

export function pickInsight(input: {
  occupation: OnboardingOccupation;
  income: number;
  debts: DraftDebt[];
  investments: DraftInvestment[];
  goals: DraftGoal[];
  lifestyle: OnboardingLifestyle;
  housingKind: HousingKind | null;
  housingPayment: number;
  cash: number;
  emergency: number;
}): { title: string; body: string; cta: string } {
  const owed = sum(input.debts.map((d) => moneyOrZero(d.owed)));
  const invested = sum(input.investments.map((i) => moneyOrZero(i.amount)));
  const cash = Number.isFinite(input.cash) && input.cash > 0 ? input.cash : 0;
  const emergency = Number.isFinite(input.emergency) && input.emergency > 0 ? input.emergency : 0;
  const assets = invested + cash + emergency;
  const net = assets - owed;
  const months = input.income > 0 ? owed / input.income : 0;
  const housing = input.housingKind && input.housingKind !== "none" ? input.housingPayment : 0;
  const houseShare = input.income > 0 ? housing / input.income : 0;
  const house = input.goals.find((g) => /house|home|down payment/i.test(g.name));
  const trip = input.goals.find((g) => /trip|travel|vacation/i.test(g.name));

  if (houseShare >= 0.4) {
    const kind = input.housingKind === "mortgage" ? "The mortgage" : "Rent";
    return {
      title: `${kind} is eating the month.`,
      body: "Housing is taking a huge slice of take-home. We'll build the rest of the budget around that number, not around a pretend one.",
      cta: "Centsio will treat housing as the first line, every month.",
    };
  }
  if (months >= 6) {
    return {
      title: "The debt is the loudest thing here.",
      body: "That's a heavy load next to what comes in each month. Through budgeting, we can work through it without pretending the rest of life doesn't exist.",
      cta: "Centsio will build a payoff plan around your real month.",
    };
  }
  if (input.income > 0 && emergency === 0) {
    return {
      title: "There's no emergency stash yet.",
      body: "Everyday cash isn't a cushion. We'll treat a real emergency fund as the first goal so a surprise doesn't wreck the month.",
      cta: "Centsio will keep that fund in view until it can cover a few months.",
    };
  }
  if (input.income > 0 && cash < input.income * 0.5 && cash < 2000 && emergency < input.income) {
    return {
      title: "Cash is tight right now.",
      body: "There's not much sitting liquid next to a month of bills. We'll treat a small cushion as the first job of the budget.",
      cta: "Centsio will watch the cash so a surprise doesn't wipe the month.",
    };
  }
  if (house) {
    const label = /^house$/i.test(house.name) ? "buying a house" : house.name;
    return {
      title: "The house should come first.",
      body: `We'll treat ${label} as your primary goal and shape the budget around getting you there.`,
      cta: "Centsio will keep that goal in front of every tradeoff.",
    };
  }
  if (net < 0) {
    return {
      title: "You're in the hole. That's a starting line.",
      body: "From what you listed, estimated net worth is negative. A clear budget is how that number turns around.",
      cta: "Centsio will show the gap closing as you go.",
    };
  }
  if (input.lifestyle === "ball" && owed > input.income * 2) {
    return {
      title: "Experiences and balances can coexist.",
      body: "You want to ball out, and there's still debt in the picture. We'll protect the fun without letting the balances quietly grow.",
      cta: "Centsio will draw the line so you can see it before you spend it.",
    };
  }
  if (input.lifestyle === "strict") {
    return {
      title: "We'll protect the savings rate.",
      body: "FIRE only works if the plan survives a real month. We'll keep the cut-the-fat version in view.",
      cta: "Centsio will flag anything that leaks the rate.",
    };
  }
  if (input.occupation === "student") {
    return {
      title: "Keep the runway simple.",
      body: "Part-time money and school is a tight window. We'll keep Centsio plain so it doesn't become another class.",
      cta: "Centsio will watch the month so you don't have to.",
    };
  }
  if (input.investments.length === 0 && input.occupation === "salaried") {
    return {
      title: "Paycheck's there. Assets aren't yet.",
      body: "A regular income is the best time to start parking money where it can grow.",
      cta: "Centsio will make a first investing step obvious.",
    };
  }
  if (trip && input.lifestyle === "ball") {
    return {
      title: "The trip is the point.",
      body: "We'll fund the experience on purpose instead of hoping leftover money covers it.",
      cta: "Centsio will treat that trip as a real line in the budget.",
    };
  }
  if (input.goals.length === 0) {
    return {
      title: "We'll pick a first target together.",
      body: "You didn't lock a goal yet. That's fine — a budget still needs a direction.",
      cta: "Centsio will suggest one from how you actually spend.",
    };
  }
  return {
    title: "We've got enough to start.",
    body: "The picture you sketched is enough to personalize Centsio — budget, goals, and how we talk to you.",
    cta: "Centsio will use this as the first read every time you ask.",
  };
}

function spoken(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  if (/[0-9]/.test(trimmed) || /IRA|401/i.test(trimmed)) return trimmed;
  return trimmed.charAt(0).toLowerCase() + trimmed.slice(1);
}

export type PromisePart = { text: string; strong?: boolean };

function bit(lead: string, highlight: string): PromisePart[] {
  return [{ text: lead }, { text: highlight, strong: true }];
}

function joinPromise(bits: PromisePart[][]): PromisePart[] {
  const unique = bits.filter((row, i) => bits.findIndex((other) => other.map((p) => p.text).join("") === row.map((p) => p.text).join("")) === i).slice(0, 3);
  if (unique.length === 0) {
    return [{ text: "Centsio will help you budget the month and keep the next goal in view." }];
  }
  const out: PromisePart[] = [{ text: "Centsio will help you " }];
  unique.forEach((row, i) => {
    if (i > 0 && unique.length === 2) out.push({ text: " and " });
    else if (i > 0 && i === unique.length - 1) out.push({ text: ", and " });
    else if (i > 0) out.push({ text: ", " });
    out.push(...row);
  });
  out.push({ text: "." });
  return out;
}

/** Line under $6.99 — personal names and amounts are marked strong. */
export function pricingPromise(input: {
  income: number;
  debts: DraftDebt[];
  goals: DraftGoal[];
  housingKind: HousingKind | null;
  housingPayment: number;
  emergency: number;
}): PromisePart[] {
  const bits: PromisePart[][] = [];
  const biggest = [...input.debts].sort((a, b) => moneyOrZero(b.owed) - moneyOrZero(a.owed))[0];
  const emergency = Number.isFinite(input.emergency) && input.emergency > 0 ? input.emergency : 0;
  const housing = input.housingKind && input.housingKind !== "none" ? input.housingPayment : 0;
  const house = input.goals.find((g) => /house|home|down payment/i.test(g.name));
  const trip = input.goals.find((g) => /trip|travel|vacation/i.test(g.name));
  const named = input.goals.find((g) => g.name.trim() && !/emergency/i.test(g.name));

  if (biggest && moneyOrZero(biggest.owed) > 0) bits.push(bit("pay off those ", spoken(biggest.name)));
  if (emergency === 0) bits.push(bit("save that ", "emergency fund"));
  else if (input.income > 0 && emergency < input.income * 3) bits.push(bit("grow that ", "emergency fund"));
  if (housing > 0) {
    const kind = input.housingKind === "mortgage" ? "mortgage" : "rent";
    bits.push(bit("budget around that ", `${dollars(housing)} ${kind}`));
  }
  if (bits.length < 3) {
    if (house) bits.push(bit("save for ", /^house$/i.test(house.name) ? "that house" : spoken(house.name)));
    else if (trip) bits.push(bit("fund ", /^trip$/i.test(trip.name) ? "that trip" : spoken(trip.name)));
    else if (named) bits.push(bit("hit ", spoken(named.name)));
  }
  return joinPromise(bits);
}
