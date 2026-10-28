import { useState, type FormEvent } from "react";
import { ApiError, createCategory, deleteCategory, renameCategory, type CategoryOption } from "../lib/api";
import { reloadCategories, useCategories } from "../lib/useCategories";

const TOP_LEVEL = "";
const fieldClass =
  "min-h-10 min-w-0 rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink outline-none focus:border-signal";

/** Settings section: the user's own categories, with add, rename and delete.
 * A new one goes under a spending group (and counts in its total and budget)
 * or stands on its own at the top level. */
export function CategoriesSettings({ token }: { token: string }) {
  const categories = useCategories(token);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState(TOP_LEVEL);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Groups take new subcategories; a leaf can't, it already has transactions on it.
  const groups = categories.filter((c) => c.type === "expense" && !c.custom && c.children.length > 0);
  const mine: { category: CategoryOption; parent: string | null }[] = categories.flatMap((c) => [
    ...(c.custom ? [{ category: c, parent: null }] : []),
    ...c.children.filter((child) => child.custom).map((child) => ({ category: child, parent: c.name })),
  ]);

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
      await createCategory(token, name, parentId || null);
      setName("");
    });
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">Your categories</h3>
      {mine.length === 0 && (
        <p className="mt-2 text-sm text-ink-faint">
          Add your own, like “Wedding” or “Kids' activities”, then pick it for a transaction or a rule.
        </p>
      )}
      <ul className="mt-2 space-y-2">
        {mine.map(({ category, parent }) => (
          <li key={category.id} className="flex items-center justify-between gap-3 rounded-[14px] border border-line p-3">
            {renaming?.id === category.id ? (
              <form
                className="flex min-w-0 flex-1 gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(category.id, async () => {
                    await renameCategory(token, category.id, renaming.name);
                    setRenaming(null);
                  });
                }}
              >
                <input
                  aria-label={`New name for ${category.name}`}
                  autoFocus
                  value={renaming.name}
                  maxLength={40}
                  onChange={(e) => setRenaming({ id: category.id, name: e.target.value })}
                  className={`${fieldClass} flex-1`}
                />
                <button
                  type="submit"
                  disabled={busyId === category.id || !renaming.name.trim()}
                  className="shrink-0 cursor-pointer text-sm font-medium text-signal disabled:opacity-60"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setRenaming(null)}
                  className="shrink-0 cursor-pointer text-sm text-ink-soft hover:text-ink"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <>
                <p className="m-0 min-w-0 text-sm text-ink">
                  <span className="font-medium">{category.name}</span>
                  {parent && <span className="text-ink-faint"> · in {parent}</span>}
                </p>
                <div className="flex shrink-0 gap-3">
                  <button
                    type="button"
                    disabled={busyId === category.id}
                    onClick={() => setRenaming({ id: category.id, name: category.name })}
                    className="cursor-pointer text-sm text-ink-soft hover:text-ink disabled:opacity-60"
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    disabled={busyId === category.id}
                    onClick={() =>
                      run(category.id, async () => {
                        const { recategorized } = await deleteCategory(token, category.id);
                        if (recategorized)
                          return `Deleted ${category.name}. ${recategorized} transaction${recategorized === 1 ? "" : "s"} went back to Bankr's category for ${recategorized === 1 ? "it" : "them"}.`;
                      })
                    }
                    className="cursor-pointer text-sm text-ink-soft hover:text-negative disabled:opacity-60"
                  >
                    Delete
                  </button>
                </div>
              </>
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
          aria-label="Where it goes"
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
          className={`${fieldClass} cursor-pointer basis-40`}
        >
          <option value={TOP_LEVEL}>On its own</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
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
