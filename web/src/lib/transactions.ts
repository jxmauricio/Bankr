import type { TransactionAccount, TransactionRow } from "./api";
import { formatMoney } from "./format";

export function accountLabel(account: TransactionAccount): string {
  const name = account.name ?? account.institution;
  return account.mask ? `${name} •••• ${account.mask}` : name;
}

export function topCategory(t: TransactionRow): string {
  return t.parent_category ?? t.category ?? "Uncategorized";
}

export function merchantOf(t: TransactionRow): string {
  return t.merchant_name ?? t.category ?? "Transaction";
}

/** Money in reads signal with a plus; money out is plain ink with a true minus. */
export function signedAmount(amount: number): { text: string; className: string } {
  return amount > 0
    ? { text: `+${formatMoney(amount)}`, className: "text-signal" }
    : { text: `−${formatMoney(Math.abs(amount))}`, className: "text-ink" };
}
