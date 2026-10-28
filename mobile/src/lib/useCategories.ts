// Copied from web/src/lib/useCategories.ts (less the picker helpers mobile
// doesn't use); keep in step until they share a package.
import { useEffect, useState } from "react";
import { fetchCategories, type CategoryNode } from "./api";
import { setCategoryColors } from "./chartColors";

// Categories only change when the user adds, renames or deletes one of their
// own: load them once, and reload everywhere after such a change.
let cache: Promise<CategoryNode[]> | null = null;
let loaded: CategoryNode[] = []; // the last list, so a first render already has it
const listeners = new Set<(c: CategoryNode[]) => void>();

/** Also fills the chart color registry: the signed-in gate awaits this. */
export function loadCategories(token: string): Promise<CategoryNode[]> {
  cache ??= fetchCategories(token).then(
    (categories) => {
      loaded = categories;
      setCategoryColors(categories);
      listeners.forEach((listener) => listener(categories));
      return categories;
    },
    (err) => {
      cache = null;
      throw err;
    },
  );
  return cache;
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
