export function formatMoney(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  return `${sign}$${Math.abs(amount).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export const GOAL_TYPE_LABELS: Record<string, string> = {
  save_amount: "Savings goal",
  pay_off_debt: "Pay off debt",
  build_emergency_fund: "Emergency fund",
};
