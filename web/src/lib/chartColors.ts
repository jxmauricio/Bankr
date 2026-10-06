/**
 * Fixed category -> color slot order, matching seed_categories.py's
 * DEFAULT_CATEGORIES. Fixed (not cycled per-render) so a category's color
 * is stable across opens, per the dataviz rule "color follows the entity."
 * Palette is the validated dark-mode categorical set (8 hues, ΔE-checked
 * against this app's #10131C surface).
 */
const CATEGORY_ORDER = [
  "Income",
  "Groceries",
  "Dining",
  "Transportation",
  "Rent & Housing",
  "Utilities",
  "Subscriptions",
  "Entertainment",
  "Shopping",
  "Health",
  "Transfer",
  "Other",
  "Restaurants",
  "Fast Food",
  "Coffee",
  "Alcohol & Bars",
  "Gas",
  "Rideshare & Taxi",
  "Public Transit",
  "Parking & Tolls",
  "Auto Maintenance",
  "Travel",
  "Loan Payments",
  "Fees",
];
export const CATEGORY_PALETTE = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
];

export function colorForCategory(name: string): string {
  const i = CATEGORY_ORDER.indexOf(name);
  return i === -1 ? "#565D72" : CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
}

export function hasCategoryColor(name: string): boolean {
  return CATEGORY_ORDER.includes(name);
}
