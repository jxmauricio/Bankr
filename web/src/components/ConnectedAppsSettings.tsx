import { useEffect, useState } from "react";
import { ApiError, fetchMcpConnections, revokeMcpConnection, type McpConnections } from "../lib/api";
import { formatRelativeTime } from "../lib/format";

/** Settings section: the URL to add Bankr to Claude or ChatGPT, and every connected app with Disconnect. */
export function ConnectedAppsSettings({ token }: { token: string }) {
  const [data, setData] = useState<McpConnections | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchMcpConnections(token)
      .then(setData)
      .catch(() => setError("Couldn't load your connected apps."));
  }, [token]);

  async function revoke(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await revokeMcpConnection(token, id);
      setData((d) => (d ? { ...d, grants: d.grants.filter((g) => g.id !== id) } : d));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't disconnect it. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.server_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked: the URL is selectable anyway.
    }
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">Connect to Claude or ChatGPT</h3>
      <p className="mt-2 text-sm text-ink-faint">
        Add Bankr as a custom connector with this URL, then sign in and choose read only or read + propose
        changes. Proposed changes wait for you to confirm them here.
      </p>
      {data && (
        <div className="mt-2 flex items-center gap-2 rounded-[14px] border border-line p-2 pl-3">
          <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-ink">{data.server_url}</code>
          <button
            type="button"
            onClick={copy}
            className="shrink-0 cursor-pointer rounded-lg px-2.5 py-1 text-sm text-signal hover:text-signal-hi"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
      <p className="mt-2 text-xs text-ink-faint">
        Claude: Settings → Connectors → Add custom connector. ChatGPT: Settings → Apps &amp; Connectors → Create.
      </p>

      <h4 className="mt-4 text-xs font-medium uppercase tracking-[0.08em] text-ink-faint">Connected apps</h4>
      {data === null && !error && <p className="mt-2 text-sm text-ink-faint">Loading…</p>}
      {data?.grants.length === 0 && <p className="mt-2 text-sm text-ink-faint">No apps connected.</p>}
      <ul className="mt-2 space-y-2">
        {data?.grants.map((g) => (
          <li key={g.id} className="flex items-start justify-between gap-3 rounded-[14px] border border-line p-3">
            <div className="min-w-0">
              <p className="m-0 truncate font-medium text-ink">{g.client_name}</p>
              <p className="m-0 mt-0.5 text-xs text-ink-faint">
                {g.scopes.includes("write") ? "Read + propose changes" : "Read only"}
                {g.redirect_host ? ` · ${g.redirect_host}` : ""}
                {` · ${g.last_used_at ? `used ${formatRelativeTime(g.last_used_at)}` : `added ${formatRelativeTime(g.created_at)}`}`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => revoke(g.id)}
              disabled={busyId === g.id}
              className="shrink-0 cursor-pointer text-sm text-ink-soft transition-colors hover:text-negative disabled:opacity-60"
            >
              {busyId === g.id ? "Disconnecting…" : "Disconnect"}
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
