import { useState, type FormEvent } from "react";
import {
  ApiError,
  createCategory,
  deleteCategory,
  renameCategory,
  setBudgetMode,
  setCategoryHidden,
  type CategoryNode,
  type CategoryOption,
} from "../lib/api";
import { reloadCategories, useCategories } from "../lib/useCategories";

const ON_ITS_OWN = "";
const fieldClass =
  "min-h-10 min-w-0 rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink outline-none focus:border-signal";
const linkClass = "cursor-pointer text-sm text-ink-soft hover:text-ink disabled:opacity-60";

/** Settings section: every spending (and excluded) group and its categories.
 * Any of them can be renamed (a built-in one for this user only, with a way
 * back); a built-in category can be hidden, sending what would land there to
 * review; the user's own can be deleted; a group with several categories can
 * be budgeted as one line or a line per category. A new category goes in a
 * group (and counts in its total and budget) or stands on its own, and can be
 * excluded from every total instead ("Work Expenses"). */
export function CategoriesSettings({ token }: { token: string }) {
  const categories = useCategories(token);
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState(ON_ITS_OWN);
  const [kind, setKind] = useState<"expense" | "excluded">("expense");
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const spending = categories.filter((c) => c.type === "expense" || c.type === "excluded");
  const groupsOfKind = spending.filter((g) => g.type === kind);

  async function run(id: string, action: () => Promise<string | void>) {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      await reloadCategories(token);
      if (message) setNotice(message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    run("new", async () => {
      await createCategory(token, name, groupId || null, kind);
      setName("");
    });
  }

  function row(item: CategoryOption, nested: boolean) {
    const busy = busyId === item.id;
    if (renaming?.id === item.id) {
      return (
        <form
          className="flex min-w-0 flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run(item.id, async () => {
              await renameCategory(token, item.id, renaming.name);
              setRenaming(null);
            });
          }}
        >
          <input
            aria-label={`New name for ${item.name}`}
            autoFocus
            value={renaming.name}
            maxLength={40}
            onChange={(e) => setRenaming({ id: item.id, name: e.target.value })}
            className={`${fieldClass} flex-1`}
          />
          <button type="submit" disabled={busy || !renaming.name.trim()} className="shrink-0 cursor-pointer text-sm font-medium text-signal disabled:opacity-60">
            Save
          </button>
          <button type="button" onClick={() => setRenaming(null)} className="shrink-0 cursor-pointer text-sm text-ink-soft hover:text-ink">
            Cancel
          </button>
        </form>
      );
    }
    return (
      <>
        <p className={`m-0 min-w-0 text-sm ${item.hidden ? "text-ink-faint" : nested ? "text-ink-soft" : "font-medium text-ink"}`}>
          {item.emoji && <span aria-hidden="true">{item.emoji} </span>}
          {item.name}
          {item.custom && <span className="font-normal text-ink-faint"> · yours</span>}
          {item.type === "excluded" && <span className="font-normal text-ink-faint"> · counts in no total</span>}
          {item.hidden && <span className="font-normal"> · hidden</span>}
        </p>
        <div className="flex shrink-0 gap-3">
          <button type="button" disabled={busy} onClick={() => setRenaming({ id: item.id, name: item.name })} className={linkClass}>
            Rename
          </button>
          {!item.custom && item.kind === "category" && item.key !== "uncategorized" && (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(item.id, async () => {
                  const { recategorized } = await setCategoryHidden(token, item.id, !item.hidden);
                  if (recategorized)
                    return `${recategorized} transaction${recategorized === 1 ? "" : "s"} ${item.hidden ? "moved back" : "moved to review"}.`;
                })
              }
              className={linkClass}
            >
              {item.hidden ? "Show" : "Hide"}
            </button>
          )}
          {item.renamed && (
            <button type="button" disabled={busy} onClick={() => run(item.id, () => renameCategory(token, item.id, "").then(() => {}))} className={linkClass}>
              Reset name
            </button>
          )}
          {item.custom && (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(item.id, async () => {
                  const { recategorized } = await deleteCategory(token, item.id);
                  if (recategorized)
                    return `Deleted ${item.name}. ${recategorized} transaction${recategorized === 1 ? "" : "s"} went back to Bankr's category for ${recategorized === 1 ? "it" : "them"}.`;
                })
              }
              className="cursor-pointer text-sm text-ink-soft hover:text-negative disabled:opacity-60"
            >
              Delete
            </button>
          )}
        </div>
      </>
    );
  }

  function budgetMode(group: CategoryNode) {
    if (group.kind !== "group" || group.children.length < 2) return null;
    return (
      <label className="mt-1 flex items-center gap-2 text-xs text-ink-faint">
        Budget
        <select
          aria-label={`How to budget ${group.name}`}
          value={group.budget_mode}
          disabled={busyId === group.id}
          onChange={(e) => {
            const mode = e.target.value as CategoryNode["budget_mode"];
            run(group.id, () => setBudgetMode(token, group.group_id, mode).then(() => {}));
          }}
          className="h-7 cursor-pointer rounded-lg border border-line bg-raised px-1.5 text-xs text-ink"
        >
          <option value="by_group">as one line</option>
          <option value="by_category">by category</option>
        </select>
      </label>
    );
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">Categories</h3>
      <p className="mt-1 text-sm text-ink-faint">
        Rename any of them, or add your own, like “Wedding” or “Kids' activities”, then pick it for a transaction or a rule.
      </p>
      <ul className="mt-2 space-y-2">
        {spending.map((group) => (
          <li key={group.id} className="rounded-[14px] border border-line p-3">
            <div className="flex items-center justify-between gap-3">{row(group, false)}</div>
            {budgetMode(group)}
            {group.children.length > 0 && (
              <ul className="mt-2 space-y-1.5 border-l border-line pl-3">
                {group.children.map((child) => (
                  <li key={child.id} className="flex items-center justify-between gap-3">
                    {row(child, true)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="mt-2 flex flex-wrap gap-2">
        <input
          aria-label="New category name"
          placeholder="New category"
          value={name}
          maxLength={40}
          onChange={(e) => setName(e.target.value)}
          className={`${fieldClass} flex-1 basis-40`}
        />
        <select
          aria-label="How it counts"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as "expense" | "excluded");
            setGroupId(ON_ITS_OWN);
          }}
          className={`${fieldClass} cursor-pointer basis-40`}
        >
          <option value="expense">Counts as spending</option>
          <option value="excluded">Excluded from totals</option>
        </select>
        <select
          aria-label="Where it goes"
          value={groupId}
          onChange={(e) => setGroupId(e.target.value)}
          className={`${fieldClass} cursor-pointer basis-40`}
        >
          <option value={ON_ITS_OWN}>On its own</option>
          {groupsOfKind.map((g) => (
            <option key={g.group_id} value={g.group_id}>
              In {g.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busyId === "new" || !name.trim()}
          className="min-h-10 cursor-pointer rounded-xl bg-signal px-3.5 text-[13px] font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
        >
          Add
        </button>
      </form>
      {notice && <p className="mt-3 text-sm text-ink-soft">{notice}</p>}
      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}
    </>
  );
}
