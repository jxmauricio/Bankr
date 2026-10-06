import { useState, type FormEvent } from "react";
import { ApiError, login, signUp } from "../lib/api";
import { useSession } from "../lib/session";

const inputClass =
  "h-12 w-full rounded-[10px] border border-control bg-surface px-3.5 text-[15px] text-ink outline-none focus:border-signal aria-[invalid=true]:border-negative";

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

  const isSignup = mode === "signup";

  return (
    <div className="flex min-h-screen flex-wrap bg-bg">
      {/* Editorial side */}
      <section className="flex min-w-0 flex-[1_1_480px] flex-col justify-between gap-8 border-line px-6 pb-0 pt-10 sm:gap-12 sm:px-14 sm:py-12 min-[960px]:border-r">
        <div className="flex items-baseline gap-2.5">
          <span className="font-display text-[26px] font-semibold tracking-tight text-ink">
            bankr<span className="text-signal">_</span>
          </span>
          <span className="font-mono text-[10px] tracking-[0.14em] text-signal">PRIVATE BETA</span>
        </div>
        <div className="flex max-w-[520px] flex-col gap-7">
          <h1 className="font-display text-[38px] font-normal leading-[1.05] tracking-[-0.02em] text-ink sm:text-[52px]">
            Ask your money anything.
            <br />
            <span className="text-ink-soft">Check every answer.</span>
          </h1>
          <figure aria-label="Example answer" className="hidden flex-col gap-3.5 rounded-[20px] border border-line bg-surface p-5 sm:flex">
            <div className="self-end rounded-[16px_16px_4px_16px] bg-user px-3.5 py-2 text-sm text-white">
              What did I spend on food in August?
            </div>
            <p className="text-sm leading-relaxed text-ink">
              You spent <span className="fig">$703.85</span>
              <sup className="font-mono text-[10px] text-signal">1</sup> — most of it at three grocery stores.
            </p>
            <div className="flex items-center gap-2 border-t border-line pt-3 text-xs text-ink-soft">
              <span className="font-mono text-signal">1</span>
              <span className="font-tabular">17 transactions · Aug 1–31 · •••• 4821</span>
            </div>
          </figure>
        </div>
        <ul className="hidden flex-wrap gap-6 text-[13px] text-ink-soft sm:flex">
          <li>Read-only bank access via Plaid</li>
          <li>Answers cite your transactions</li>
          <li>Delete your data anytime</li>
        </ul>
      </section>

      {/* Form side */}
      <section className="flex min-w-0 flex-[1_1_420px] items-center justify-center px-6 py-10 sm:py-12">
        <form onSubmit={handleSubmit} className="flex w-full max-w-[380px] flex-col gap-5">
          <div role="tablist" aria-label="Account" className="grid grid-cols-2 border-b border-line">
            {(["login", "signup"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
                className={`h-12 cursor-pointer border-b-2 text-[15px] transition-colors ${
                  mode === m ? "border-ink font-medium text-ink" : "border-transparent text-ink-soft hover:text-ink"
                }`}
              >
                {m === "signup" ? "Create account" : "Sign in"}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-1.5">
            <h2 className="font-display text-[28px] font-normal text-ink">
              {isSignup ? "Join the beta" : "Welcome back"}
            </h2>
            <p className="text-sm text-ink-soft">
              {isSignup ? "Create an account with your invite code." : "Sign in to pick up your conversation."}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-[13px] text-ink-soft">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-[13px] text-ink-soft">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete={isSignup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={Boolean(error) && !isSignup}
              aria-describedby={error ? "auth-error" : isSignup ? "pw-hint" : undefined}
              className={inputClass}
            />
            {isSignup && (
              <span id="pw-hint" className="text-xs text-ink-faint">
                At least 8 characters.
              </span>
            )}
          </div>
          {isSignup && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="invite" className="text-[13px] text-ink-soft">
                Invite code
              </label>
              <input
                id="invite"
                type="text"
                autoComplete="off"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                className={inputClass}
              />
            </div>
          )}

          {error && (
            <p id="auth-error" role="alert" className="text-[13px] text-negative">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isBusy}
            className="h-12 cursor-pointer rounded-[10px] bg-ink text-[15px] font-medium text-bg transition-opacity disabled:opacity-60"
          >
            {isBusy ? "One moment…" : isSignup ? "Create account" : "Sign in"}
          </button>
          <p className="text-xs leading-relaxed text-ink-faint">
            By continuing you agree to the{" "}
            <a href="/privacy" className="text-signal hover:text-signal-hi">
              Privacy notice
            </a>
            . Bankr is in private beta.
          </p>
        </form>
      </section>
    </div>
  );
}
