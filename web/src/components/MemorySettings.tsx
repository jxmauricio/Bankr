import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  createMemoryFact,
  deleteMemoryFact,
  fetchMemory,
  updateMemoryFact,
  type MemoryFact,
  type MemoryList,
} from "../lib/api";

const fieldClass =
  "min-h-10 min-w-0 rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink outline-none focus:border-signal";
const linkClass = "cursor-pointer text-sm text-ink-soft hover:text-ink disabled:opacity-60";

/** Settings section: what Bankr remembers about the user across chats (pay
 * schedule, priorities, household). The assistant sees these on every
 * message and can only suggest new ones on a card; here the user can add,
 * edit and delete them directly. */
export function MemorySettings({ token }: { token: string }) {
  const [memory, setMemory] = useState<MemoryList | null>(null);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("income");
  const [editing, setEditing] = useState<{ id: string; text: string; kind: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMemory(token)
      .then(setMemory)
      .catch(() => setError("Couldn't load what Bankr remembers."));
  }, [token]);

  async function run(id: string, action: () => Promise<void>) {
    setBusyId(id);
    setError(null);
    try {
      await action();
      setMemory(await fetchMemory(token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    run("new", async () => {
      await createMemoryFact(token, { text, kind });
      setText("");
    });
  }

  function save(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    run(editing.id, async () => {
      await updateMemoryFact(token, editing.id, { text: editing.text, kind: editing.kind });
      setEditing(null);
    });
  }

  const kinds = Object.entries(memory?.kinds ?? {});
  const atLimit = memory !== null && memory.facts.length >= memory.max_facts;

  function kindSelect(value: string, onChange: (kind: string) => void, label: string) {
    return (
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={`${fieldClass} cursor-pointer`}>
        {kinds.map(([key, name]) => (
          <option key={key} value={key}>
            {name}
          </option>
        ))}
      </select>
    );
  }

  function row(fact: MemoryFact) {
    const busy = busyId === fact.id;
    if (editing?.id === fact.id) {
      return (
        <form onSubmit={save} className="flex flex-wrap gap-2">
          <input
            aria-label="Edit memory"
            autoFocus
            value={editing.text}
            maxLength={memory?.max_chars}
            onChange={(e) => setEditing({ ...editing, text: e.target.value })}
            className={`${fieldClass} flex-1 basis-48`}
          />
          {kindSelect(editing.kind, (k) => setEditing({ ...editing, kind: k }), "Kind of memory")}
          <div className="flex items-center gap-3">
            <button type="submit" disabled={busy || !editing.text.trim()} className="cursor-pointer text-sm font-medium text-signal disabled:opacity-60">
              Save
            </button>
            <button type="button" onClick={() => setEditing(null)} className={linkClass}>
              Cancel
            </button>
          </div>
        </form>
      );
    }
    return (
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-sm text-ink">{fact.text}</p>
          <p className="m-0 mt-0.5 text-xs text-ink-faint">
            {memory?.kinds[fact.kind] ?? fact.kind}
            {fact.source === "agent" && " · suggested in chat"}
          </p>
        </div>
        <div className="flex shrink-0 gap-3">
          <button type="button" disabled={busy} onClick={() => setEditing({ id: fact.id, text: fact.text, kind: fact.kind })} className={linkClass}>
            Edit
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(fact.id, () => deleteMemoryFact(token, fact.id))}
            className="cursor-pointer text-sm text-ink-soft hover:text-negative disabled:opacity-60"
          >
            Delete
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <h3 className="mt-6 text-sm font-medium text-ink-soft">What Bankr knows about you</h3>
      <p className="mt-1 text-xs text-ink-faint">
        The assistant keeps these in mind in every chat. It only adds one when you confirm, and never stores account
        numbers or passwords. Your numbers always come from your accounts, not from here.
      </p>
      {memory === null && !error && <p className="mt-2 text-sm text-ink-faint">Loading…</p>}
      {memory?.facts.length === 0 && (
        <p className="mt-2 text-sm text-ink-faint">Nothing yet. Add your pay schedule or what you're saving for.</p>
      )}
      <ul className="mt-2 space-y-2">
        {memory?.facts.map((fact) => (
          <li key={fact.id} className="rounded-[14px] border border-line p-3">
            {row(fact)}
          </li>
        ))}
      </ul>
      {memory && !atLimit && (
        <form onSubmit={add} className="mt-2 flex flex-wrap gap-2">
          <input
            aria-label="Something for Bankr to remember"
            placeholder="e.g. Paid every other Friday"
            value={text}
            maxLength={memory.max_chars}
            onChange={(e) => setText(e.target.value)}
            className={`${fieldClass} flex-1 basis-48`}
          />
          {kindSelect(kind, setKind, "Kind of memory")}
          <button
            type="submit"
            disabled={busyId === "new" || !text.trim()}
            className="min-h-10 cursor-pointer rounded-xl bg-signal px-3.5 text-[13px] font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
          >
            Add
          </button>
        </form>
      )}
      {atLimit && (
        <p className="mt-2 text-xs text-ink-faint">That's the limit of {memory?.max_facts}. Delete one to add another.</p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}
    </>
  );
}
