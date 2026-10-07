import { useEffect, useState } from "react";
import { ApiError, deleteRule, fetchRules, updateRule, type Rule } from "../lib/api";
import { formatMoney } from "../lib/format";
import { useCategories } from "../lib/useCategories";
import { CategorySelect } from "./CategorySelect";

function amountRange(rule: Rule): string | null {
  const { amount_min: lo, amount_max: hi } = rule;
  if (lo != null && hi != null) return `${formatMoney(lo)}–${formatMoney(hi)}`;
  if (lo != null) return `${formatMoney(lo)}+`;
  if (hi != null) return `up to ${formatMoney(hi)}`;
  return null;
}

/** Settings section: every categorization rule, with change-category and delete. */
export function RulesSettings({ token }: { token: string }) {
  const categories = useCategories(token);
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    fetchRules(token)
      .then(setRules)
      .catch(() => setError("Couldn't load your rules."));
  }, [token]);

  async function run(id: string, action: () => Promise<void>) {
    setBusyId(id);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">Categorization rules</h3>
      {rules === null && !error && <p className="mt-2 text-sm text-ink-faint">Loading…</p>}
      {rules?.length === 0 && (
        <p className="mt-2 text-sm text-ink-faint">
          No rules yet. Change a transaction's category and Bankr will offer to remember it.
        </p>
      )}
      <ul className="mt-2 space-y-2">
        {rules?.map((rule) => {
          const range = amountRange(rule);
          return (
            <li key={rule.id} className="flex flex-col gap-2 rounded-[14px] border border-line p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="m-0 min-w-0 text-sm text-ink">
                  Merchant contains <span className="font-medium">“{rule.merchant_contains}”</span>
                  {range && <span className="text-ink-faint"> · {range}</span>}
                  {rule.set_merchant_name && <span className="text-ink-faint"> · shown as {rule.set_merchant_name}</span>}
                </p>
                <button
                  type="button"
                  disabled={busyId === rule.id}
                  onClick={() =>
                    run(rule.id, async () => {
                      await deleteRule(token, rule.id);
                      setRules((rs) => rs?.filter((r) => r.id !== rule.id) ?? null);
                    })
                  }
                  className="shrink-0 cursor-pointer text-sm text-ink-soft hover:text-negative disabled:opacity-60"
                >
                  Delete
                </button>
              </div>
              <CategorySelect
                label={`Category for ${rule.merchant_contains}`}
                categories={categories}
                value={rule.set_category_id}
                disabled={busyId === rule.id}
                onChange={(id) =>
                  run(rule.id, async () => {
                    const updated = await updateRule(token, rule.id, { set_category_id: id });
                    setRules((rs) => rs?.map((r) => (r.id === rule.id ? updated : r)) ?? null);
                  })
                }
              />
            </li>
          );
        })}
      </ul>
      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}
    </>
  );
}
