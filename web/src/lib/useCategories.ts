import { useEffect, useState } from "react";
import { fetchCategories, type CategoryNode } from "./api";
import { setCategoryColors } from "./chartColors";

// Categories only change when the user adds, renames or deletes one of their
// own: load them once per page, and reload everywhere after such a change.
let cache: Promise<CategoryNode[]> | null = null;
let loaded: CategoryNode[] = []; // the last list, so a first render already has it
const listeners = new Set<(c: CategoryNode[]) => void>();

/** Also fills the chart color registry: the boot screen awaits this. */
export function loadCategories(token: string): Promise<CategoryNode[]> {
  cache ??= fetchCategories(token).then(
    (categories) => {
      loaded = categories;
      setCategoryColors(categories);
      return categories;
    },
    (err) => {
      cache = null;
      throw err;
    },
  );
  return cache;
}

/** Call after changing a category: every mounted picker gets the new list. */
export async function reloadCategories(token: string): Promise<CategoryNode[]> {
  cache = null;
  const categories = await loadCategories(token);
  listeners.forEach((listener) => listener(categories));
  return categories;
}

export function useCategories(token: string | null): CategoryNode[] {
  const [categories, setCategories] = useState<CategoryNode[]>(loaded);
  useEffect(() => {
    if (!token) return;
    let stale = false;
    const update = (c: CategoryNode[]) => !stale && setCategories(c);
    listeners.add(update);
    loadCategories(token).then(update).catch(() => {});
    return () => {
      stale = true;
      listeners.delete(update);
    };
  }, [token]);
  return categories;
}

/** Native <select> options, categories indented under their group. A group
 * is only a heading: transactions always go on one of its categories, and
 * the backend rejects the group. */
export function categoryOptions(
  categories: CategoryNode[],
): { id: string; label: string; group: string; disabled: boolean }[] {
  const groupName = { expense: "Spending", income: "Income", transfer: "Transfers", excluded: "Excluded" } as const;
  return categories.filter((c) => !c.hidden).flatMap((c) => [
    { id: c.id, label: `${c.emoji ? `${c.emoji} ` : ""}${c.name}`, group: groupName[c.type], disabled: c.kind === "group" },
    ...c.children.filter((child) => !child.hidden).map((child) => ({
      id: child.id,
      label: `  ${child.emoji ? `${child.emoji} ` : ""}${child.name}`,
      group: groupName[c.type],
      disabled: false,
    })),
  ]);
}

/** Spending categories by name, each group followed by its subcategories:
 * what a spending tracker can watch. */
export function spendCategoryNames(categories: CategoryNode[]): string[] {
  return categories.filter((c) => c.type === "expense").flatMap((c) => [c.name, ...c.children.map((k) => k.name)]);
}

/** The current name for a category given by key ("restaurants") or name:
 * goal proposals name categories by key, so they survive a rename. */
export function categoryName(categories: CategoryNode[], keyOrName: string): string {
  const all = categories.flatMap((c) => [c, ...c.children]);
  return all.find((c) => c.key === keyOrName)?.name ?? keyOrName;
}

/** What a budget line can cover, as the backend keys its lines: a spending
 * group, or each category of a group the user budgets by category. */
export function budgetTargets(categories: CategoryNode[]): { id: string; name: string }[] {
  return categories
    .filter((c) => c.type === "expense")
    .flatMap((c) =>
      c.budget_mode === "by_category" && c.kind === "group"
        ? c.children.map((k) => ({ id: k.id, name: k.name }))
        : [{ id: c.group_id, name: c.name }],
    );
}
