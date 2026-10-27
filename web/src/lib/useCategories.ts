import { useEffect, useState } from "react";
import { fetchCategories, type CategoryNode } from "./api";

// Categories are global and never change at runtime: load them once per page.
let cache: Promise<CategoryNode[]> | null = null;

export function useCategories(token: string | null): CategoryNode[] {
  const [categories, setCategories] = useState<CategoryNode[]>([]);
  useEffect(() => {
    if (!token) return;
    let stale = false;
    cache ??= fetchCategories(token).catch((err) => {
      cache = null;
      throw err;
    });
    cache.then((c) => !stale && setCategories(c)).catch(() => {});
    return () => {
      stale = true;
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
