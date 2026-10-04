import { useEffect, useState, type FormEvent } from "react";
import { AddBankButton } from "./AddBankButton";
import { ApiError, deleteAccount, disconnectBank, fetchLinkedBanks, type LinkedBank } from "../lib/api";

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: "Checking",
  savings: "Savings",
  credit: "Credit card",
  loan: "Loan",
  investment: "Investment",
};

// A bank like Chase can hold a dozen accounts; a run-on list of all of them
// buries the Disconnect button. Name the first few and count the rest.
const MAX_ACCOUNTS_SHOWN = 3;

function describeAccounts(accounts: LinkedBank["accounts"]) {
  const shown = accounts.slice(0, MAX_ACCOUNTS_SHOWN).map(describeAccount);
  const hidden = accounts.length - shown.length;
  return hidden > 0 ? `${shown.join(" · ")} · +${hidden} more` : shown.join(" · ");
}

function describeAccount(a: LinkedBank["accounts"][number]) {
  const label = a.name || ACCOUNT_TYPE_LABELS[a.account_type] || a.account_type;
  return a.mask ? `${label} ··${a.mask}` : label;
}

export function SettingsModal({
  token,
  onClose,
  onBanksChanged,
  onAccountDeleted,
}: {
  token: string;
  onClose: () => void;
  /** Called after a bank is connected or disconnected, with how many remain. */
  onBanksChanged: (remaining: number) => void | Promise<void>;
  onAccountDeleted: () => void;
}) {
  const [banks, setBanks] = useState<LinkedBank[] | null>(null);
  const [confirmingBankId, setConfirmingBankId] = useState<string | null>(null);
  const [busyBankId, setBusyBankId] = useState<string | null>(null);
  const [bankError, setBankError] = useState<string | null>(null);
  const [isLinking, setIsLinking] = useState(false);

  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const isBusy = busyBankId !== null || isDeleting || isLinking;

  useEffect(() => {
    fetchLinkedBanks(token)
      .then(setBanks)
      .catch(() => setBankError("Couldn't load your banks. Check your connection and try again."));
  }, [token]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isBusy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, isBusy]);

  async function handleDisconnect(bank: LinkedBank) {
    setBusyBankId(bank.id);
    setBankError(null);
    try {
      await disconnectBank(token, bank.id);
      const remaining = (banks ?? []).filter((b) => b.id !== bank.id);
      setBanks(remaining);
      setConfirmingBankId(null);
      await onBanksChanged(remaining.length);
    } catch (err) {
      setBankError(err instanceof ApiError ? err.message : "Couldn't disconnect this bank. Try again.");
    } finally {
      setBusyBankId(null);
    }
  }

  async function handleDelete(e: FormEvent) {
    e.preventDefault();
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteAccount(token, password);
      onAccountDeleted();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete your account. Try again.");
      setIsDeleting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4"
      onClick={() => {
        if (!isBusy) onClose();
      }}
      role="presentation"
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-3xl border border-line-strong bg-surface shadow-modal p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="flex items-center justify-between">
          <h2 id="settings-title" className="font-display text-lg font-semibold text-ink">
            Settings
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isBusy}
            className="text-sm text-ink-soft transition-colors hover:text-ink disabled:opacity-60 cursor-pointer"
          >
            Close
          </button>
        </div>

        <h3 className="mt-5 text-sm font-medium text-ink-soft">Connected banks</h3>
        {banks === null && !bankError && <p className="mt-2 text-sm text-ink-faint">Loading…</p>}
        {banks?.length === 0 && <p className="mt-2 text-sm text-ink-faint">No banks connected.</p>}
        <ul className="mt-2 space-y-2">
          {banks?.map((bank) => (
            <li key={bank.id} className="rounded-[14px] border border-line p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{bank.institution_name}</p>
                  <p className="mt-0.5 text-xs text-ink-faint">{describeAccounts(bank.accounts)}</p>
                  {bank.status === "error" && (
                    <p className="mt-1 text-xs text-negative">Needs attention: sign in to this bank again.</p>
                  )}
                </div>
                {confirmingBankId !== bank.id && (
                  <button
                    type="button"
                    onClick={() => setConfirmingBankId(bank.id)}
                    disabled={isBusy}
                    className="shrink-0 text-sm text-ink-soft transition-colors hover:text-negative disabled:opacity-60 cursor-pointer"
                  >
                    Disconnect
                  </button>
                )}
              </div>
              {confirmingBankId === bank.id && (
                <div className="mt-3 rounded-xl bg-raised p-3">
                  <p className="text-sm text-ink-soft">
                    This removes {bank.institution_name} and its transactions from Bankr. You can link it again later.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleDisconnect(bank)}
                      disabled={isBusy}
                      className="rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 cursor-pointer"
                    >
                      {busyBankId === bank.id ? "Disconnecting…" : "Disconnect"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingBankId(null)}
                      disabled={isBusy}
                      className="rounded-lg px-3 py-1.5 text-sm text-ink-soft hover:text-ink disabled:opacity-60 cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
        {bankError && (
          <p role="alert" className="mt-3 text-sm text-negative">
            {bankError}
          </p>
        )}
        <AddBankButton
          token={token}
          disabled={busyBankId !== null || isDeleting}
          onBusyChange={setIsLinking}
          onLinked={async () => {
            const updated = await fetchLinkedBanks(token);
            setBanks(updated);
            await onBanksChanged(updated.length);
          }}
        />

        <p className="mt-6 text-sm">
          <a href="/privacy" target="_blank" rel="noreferrer" className="text-ink-soft underline hover:text-ink">
            Privacy notice
          </a>
        </p>

        <div className="mt-8 border-t border-border pt-5">
          <h3 className="text-sm font-medium text-ink-soft">Delete account</h3>
          {!deleting ? (
            <>
              <p className="mt-2 text-sm text-ink-faint">
                Permanently deletes your Bankr account, goals, chat history and every connected bank.
              </p>
              <button
                type="button"
                onClick={() => setDeleting(true)}
                disabled={isBusy}
                className="mt-3 rounded-lg border border-danger px-3 py-1.5 text-sm font-medium text-negative transition-colors hover:bg-negative-soft disabled:opacity-60 cursor-pointer"
              >
                Delete my account…
              </button>
            </>
          ) : (
            <form onSubmit={handleDelete} className="mt-2">
              <p className="text-sm text-ink-soft">
                This can't be undone. Enter your password to confirm.
              </p>
              <label htmlFor="delete-password" className="sr-only">
                Password
              </label>
              <input
                id="delete-password"
                type="password"
                required
                autoFocus
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-3 w-full min-h-11 rounded-[14px] border border-control bg-surface px-3.5 py-2 text-ink outline-none focus:border-danger focus:ring-2 focus:ring-danger-soft"
              />
              {deleteError && (
                <p role="alert" className="mt-2 text-sm text-negative">
                  {deleteError}
                </p>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  type="submit"
                  disabled={isBusy || password === ""}
                  className="rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 cursor-pointer"
                >
                  {isDeleting ? "Deleting…" : "Permanently delete"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDeleting(false);
                    setPassword("");
                    setDeleteError(null);
                  }}
                  disabled={isBusy}
                  className="rounded-lg px-3 py-1.5 text-sm text-ink-soft hover:text-ink disabled:opacity-60 cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
