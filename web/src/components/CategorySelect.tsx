import type { CategoryNode } from "../lib/api";
import { categoryOptions } from "../lib/useCategories";

/** A native select of every category, grouped Spending / Income / Transfers. */
export function CategorySelect({
  categories,
  value,
  onChange,
  label,
  disabled,
  className = "",
}: {
  categories: CategoryNode[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  const options = categoryOptions(categories);
  const groups = [...new Set(options.map((o) => o.group))];
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled || !categories.length}
      onChange={(e) => onChange(e.target.value)}
      className={`h-10 min-w-0 cursor-pointer rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink outline-none focus:border-signal disabled:opacity-50 ${className}`}
    >
      {!value && <option value="">Choose a category</option>}
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {options
            .filter((o) => o.group === g)
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  );
}
