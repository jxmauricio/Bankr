import { useEffect, useState } from "react";
import { ApiError, createRule, previewRule, type CategoryNode, type TransactionRow } from "../lib/api";

function categoryName(categories: CategoryNode[], id: string): string {
  for (const c of categories) {
    if (c.id === id) return c.name;
    const child = c.children.find((k) => k.id === id);
    if (child) return child.name;
  }
  return "this category";
}

/**
 * Shown right after a recategorization: "Always put <merchant> here?" One
 * tap makes a rule and applies it to past transactions too.
 */
export function RuleOffer({
  token,
  txn,
  categoryId,
  categories,
  onApplied,
}: {
  token: string;
  txn: TransactionRow;
  categoryId: string;
  categories: CategoryNode[];
  /** The rule was made; `changed` other rows were recategorized. */
  onApplied: (changed: number) => void;
}) {
  // Match the bank's name: it's what future charges will arrive as.
  const merchant = txn.original_merchant_name ?? txn.merchant_name ?? "";
  const [count, setCount] = useState<number | null>(null);
  const [state, setState] = useState<"offer" | "busy" | "done" | "dismissed">("offer");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (merchant.length < 2) return;
    let stale = false;
    previewRule(token, merchant, categoryId)
      .then((n) => !stale && setCount(n))
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [token, merchant, categoryId]);

  if (merchant.length < 2 || state === "dismissed") return null;
  const name = categoryName(categories, categoryId);

  if (state === "done") {
    return <p className="m-0 rounded-xl bg-signal-wash px-3 py-2.5 text-xs text-ink">Done. {merchant} will always go to {name}.</p>;
  }

  async function accept() {
    setState("busy");
    setError(null);
    try {
      const rule = await createRule(token, { merchant_contains: merchant, set_category_id: categoryId, apply_to_existing: true });
      setState("done");
      onApplied(rule.applied_to ?? 0);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't make the rule. Try again.");
      setState("offer");
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <p className="m-0 text-[13px] text-ink">
        Always put <span className="font-semibold">{merchant}</span> in {name}?
        {count ? (
          <span className="text-ink-soft">
            {" "}
            Also updates {count} past transaction{count === 1 ? "" : "s"}.
          </span>
        ) : null}
      </p>
      {error && <p className="m-0 text-xs text-negative">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={state === "busy"}
          onClick={accept}
          className="h-9 cursor-pointer rounded-lg bg-signal px-3 text-xs font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
        >
          {state === "busy" ? "Saving…" : "Make it a rule"}
        </button>
        <button
          type="button"
          onClick={() => setState("dismissed")}
          className="h-9 cursor-pointer rounded-lg px-3 text-xs text-ink-soft hover:text-ink"
        >
          Just this one
        </button>
      </div>
    </div>
  );
}
