import { useEffect, useState } from "react";
import { fetchCategories, type CategoryNode } from "./api";

// Categories only change when the user adds, renames or deletes one of their
// own: load them once per page, and reload everywhere after such a change.
let cache: Promise<CategoryNode[]> | null = null;
const listeners = new Set<(c: CategoryNode[]) => void>();

function load(token: string): Promise<CategoryNode[]> {
  cache ??= fetchCategories(token).catch((err) => {
    cache = null;
    throw err;
  });
  return cache;
}

/** Call after changing a category: every mounted picker gets the new list. */
export async function reloadCategories(token: string): Promise<CategoryNode[]> {
  cache = null;
  const categories = await load(token);
  listeners.forEach((listener) => listener(categories));
  return categories;
}

export function useCategories(token: string | null): CategoryNode[] {
  const [categories, setCategories] = useState<CategoryNode[]>([]);
  useEffect(() => {
    if (!token) return;
    let stale = false;
    const update = (c: CategoryNode[]) => !stale && setCategories(c);
    listeners.add(update);
    load(token).then(update).catch(() => {});
    return () => {
      stale = true;
      listeners.delete(update);
    };
  }, [token]);
  return categories;
}

/** Native <select> options, subcategories indented under their parent. A
 * parent with subcategories is only a heading: transactions always go on one
 * of its subcategories, and the backend rejects the parent. */
export function categoryOptions(
  categories: CategoryNode[],
): { id: string; label: string; group: string; disabled: boolean }[] {
  const groupName = { expense: "Spending", income: "Income", transfer: "Transfers" } as const;
  return categories.flatMap((c) => [
    { id: c.id, label: c.name, group: groupName[c.type], disabled: c.children.length > 0 },
    ...c.children.map((child) => ({
      id: child.id,
      label: `  ${child.name}`,
      group: groupName[c.type],
      disabled: false,
    })),
  ]);
}
