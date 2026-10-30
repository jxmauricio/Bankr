import { useEffect, useState } from "react";
import { fetchNotificationSettings, updateNotificationSettings, type NotificationSettings as Prefs } from "../lib/api";

const KINDS: { key: "daily_briefing" | "weekly_recap"; label: string; detail: string }[] = [
  { key: "daily_briefing", label: "Daily briefing", detail: "Mornings, when something needs a look." },
  { key: "weekly_recap", label: "Weekly recap", detail: "Sunday evenings." },
];

/** Settings section: which pushes the phone app gets. */
export function NotificationSettings({ token }: { token: string }) {
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNotificationSettings(token)
      .then(setPrefs)
      .catch(() => setError("Couldn't load notification settings."));
  }, [token]);

  async function toggle(key: "daily_briefing" | "weekly_recap") {
    if (!prefs) return;
    const next = !prefs[key];
    setPrefs({ ...prefs, [key]: next });
    setError(null);
    try {
      setPrefs(await updateNotificationSettings(token, { [key]: next }));
    } catch {
      setPrefs({ ...prefs, [key]: !next });
      setError("Couldn't save that. Try again.");
    }
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">Push notifications</h3>
      <p className="mt-1 text-xs text-ink-faint">
        {prefs?.device_count
          ? `Sent to the Bankr app on ${prefs.device_count === 1 ? "your phone" : `${prefs.device_count} phones`}.`
          : "Sent to the Bankr phone app once you allow notifications there."}
      </p>
      <ul className="mt-2 space-y-1">
        {KINDS.map(({ key, label, detail }) => (
          <li key={key} className="flex items-center justify-between gap-3 py-1.5">
            <div className="min-w-0">
              <p className="text-sm text-ink">{label}</p>
              <p className="text-xs text-ink-faint">{detail}</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={prefs?.[key] ?? false}
              aria-label={label}
              disabled={!prefs}
              onClick={() => toggle(key)}
              className={`relative h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors disabled:opacity-50 ${
                prefs?.[key] ? "bg-signal" : "bg-line-strong"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-[left] ${prefs?.[key] ? "left-[18px]" : "left-0.5"}`}
              />
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="mt-2 text-sm text-negative">
          {error}
        </p>
      )}
    </>
  );
}
