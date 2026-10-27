/**
 * Fixed category -> color slot order over seed_categories.py's
 * DEFAULT_CATEGORIES, most-seen spending first so those get distinct hues.
 * Fixed (not cycled per-render) so a category's color
 * is stable across opens, per the dataviz rule "color follows the entity."
 * Palette is the validated dark-mode categorical set (8 hues, ΔE-checked
 * against this app's #10131C surface).
 */
const CATEGORY_ORDER = [
  "Food & Drink",
  "Transportation",
  "Rent & Utilities",
  "General Merchandise",
  "Entertainment",
  "Travel",
  "Medical",
  "Personal Care",
  "Income",
  "Transfer In",
  "Transfer Out",
  "Loan Payments",
  "Bank Fees",
  "Home Improvement",
  "General Services",
  "Government & Non-Profit",
  "Groceries",
  "Coffee",
  "Gas",
  "Rent",
  "Utilities",
  "Software",
  "Restaurants",
  "Clothing",
  "Online Marketplaces",
  "Superstores",
  "Insurance",
  "Mortgage",
  "Rideshare & Taxis",
  "Car Maintenance",
  "Pets",
  "Alcohol & Bars",
  "Electronics",
  "Childcare",
  "Education",
  "Taxes",
  "Donations",
  "Public Transit",
  "Parking & Tolls",
  "Car Payment",
  "Student Loans",
  "Other Food & Drink",
  "Other Shopping",
  "Other Services",
  "Other Transportation",
  "Government Fees",
  "Other Loan Payments",
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
