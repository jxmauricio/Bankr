import { SAVE_NAME_SUGGESTIONS } from "../lib/format";

export function GoalNameField({
  id,
  value,
  onChange,
  suggestions = false,
  placeholder,
  labelClassName = "mb-1 block text-xs font-medium text-ink-soft",
}: {
  id: string;
  value: string;
  onChange: (name: string) => void;
  suggestions?: boolean;
  placeholder?: string;
  labelClassName?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className={labelClassName}>
        Name
      </label>
      {suggestions && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SAVE_NAME_SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onChange(suggestion)}
              className={`rounded-full border px-2.5 py-1 text-xs transition-colors cursor-pointer ${
                value === suggestion
                  ? "border-accent bg-accent-soft text-ink"
                  : "border-border bg-bg text-ink-soft hover:border-ink-faint hover:text-ink"
              }`}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? (suggestions ? "Or name it yourself" : "Name this tracker")}
        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent"
      />
    </div>
  );
}
