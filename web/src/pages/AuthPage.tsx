import { useState, type FormEvent } from "react";
import { ApiError, login, signUp } from "../lib/api";
import { useSession } from "../lib/session";

export function AuthPage() {
  const { signIn } = useSession();
  const [mode, setMode] = useState<"signup" | "login">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Invite links look like /?invite=CODE so friends don't have to type it.
  const [inviteCode, setInviteCode] = useState(() => new URLSearchParams(window.location.search).get("invite") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsBusy(true);
    try {
      const response = mode === "signup" ? await signUp(email, password, inviteCode) : await login(email, password);
      signIn(response.session_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach Bankr. Check your connection.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-10 text-center">
          <h1 className="font-display text-4xl font-semibold tracking-tight text-ink">
            bankr<span className="text-signal">_</span>
          </h1>
          <p className="mt-2 text-ink-soft">Ask your money anything. Every answer shows its source.</p>
          <span className="mt-4 inline-block rounded-full bg-signal-wash px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] text-signal">PRIVATE BETA</span>
        </div>

        <div className="rounded-3xl bg-surface p-6">
          <div className="mb-6 flex rounded-full bg-raised p-1 text-sm font-medium">
            {(["signup", "login"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
                className={`flex-1 rounded-full py-1.5 transition-colors cursor-pointer ${
                  mode === m ? "bg-signal text-bg" : "text-ink-soft"
                }`}
              >
                {m === "signup" ? "Create account" : "Sign in"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink-soft">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full min-h-11 rounded-[14px] border border-control bg-surface px-3.5 py-2 text-ink outline-none focus:border-accent "
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink-soft">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full min-h-11 rounded-[14px] border border-control bg-surface px-3.5 py-2 text-ink outline-none focus:border-accent "
              />
              {mode === "signup" && <p className="mt-1.5 text-xs text-ink-faint">At least 8 characters.</p>}
            </div>
            {mode === "signup" && (
              <div>
                <label htmlFor="invite" className="mb-1.5 block text-sm font-medium text-ink-soft">
                  Invite code
                </label>
                <input
                  id="invite"
                  type="text"
                  autoComplete="off"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  className="w-full min-h-11 rounded-[14px] border border-control bg-surface px-3.5 py-2 text-ink outline-none focus:border-accent "
                />
              </div>
            )}

            {error && (
              <p role="alert" className="text-sm text-negative">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={isBusy}
              className="w-full rounded-[14px] bg-accent py-2.5 font-medium text-bg transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
            >
              {isBusy ? "One moment…" : mode === "signup" ? "Create account" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-ink-faint">
          <a href="/privacy" className="underline transition-colors hover:text-ink-soft">
            How Bankr handles your data
          </a>
        </p>
      </div>
    </div>
  );
}
