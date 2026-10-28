// Copied from web/src/lib/chartColors.ts; keep in step until they share a package.
import type { CategoryNode } from "./api";

/**
 * Category colors come from the backend (seed_categories.category_color),
 * fixed per category so a color is stable across screens and visits, per the
 * dataviz rule "color follows the entity". This registry maps the names the
 * other endpoints send to those colors; useCategories fills it on sign-in,
 * before any chart renders, and again after a category changes.
 */
const UNCOLORED = "#565D72";
let colors = new Map<string, string>();

export function setCategoryColors(categories: CategoryNode[]) {
  colors = new Map(categories.flatMap((c) => [[c.name, c.color] as const, ...c.children.map((k) => [k.name, k.color] as const)]));
}

export function colorForCategory(name: string): string {
  return colors.get(name) ?? UNCOLORED;
}

/** A built-in category with a color of its own (the user's are grey). */
export function hasCategoryColor(name: string): boolean {
  const color = colors.get(name);
  return color !== undefined && color !== UNCOLORED;
}
