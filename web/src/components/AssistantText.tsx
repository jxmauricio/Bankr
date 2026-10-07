import type { ReactNode } from "react";
import type { ChatSource, Citation, SourceQuery } from "../lib/api";

/** How a reply's dollar figures link back to the sources under it. */
export interface FigureSources {
  citations: Citation[];
  sources: ChatSource[];
  onOpen: (query: SourceQuery) => void;
}

/**
 * Renders the agent's reply. The system prompt allows exactly two pieces of
 * markup: **bold** for the key number and "- " bullet lines for breakdowns,
 * comparisons and transactions. This renders those two and treats everything
 * else as plain text -- it is not a general-purpose markdown parser.
 *
 * Every dollar figure the server matched to a tool result (ChatResponse
 * .citations) is underlined and numbered to that source; a figure no source
 * holds renders as a plain number, so the underline only ever means "checked".
 */
export function AssistantText({ text, figures }: { text: string; figures?: FigureSources }) {
  const lines = text.split(/\n+/).filter((line) => line.trim());

  // Group consecutive "- " lines into one list; everything else is a paragraph.
  const blocks: Array<{ kind: "p"; line: string } | { kind: "ul"; items: string[] }> = [];
  for (const line of lines) {
    const bullet = line.match(/^\s*[-•]\s+(.*)$/);
    const last = blocks[blocks.length - 1];
    if (bullet) {
      if (last?.kind === "ul") last.items.push(bullet[1]);
      else blocks.push({ kind: "ul", items: [bullet[1]] });
    } else {
      blocks.push({ kind: "p", line });
    }
  }

  return (
    <div className="space-y-2">
      {blocks.map((block, i) =>
        block.kind === "p" ? (
          <p key={i}>{renderBold(block.line, figures)}</p>
        ) : (
          <ul key={i} className="list-disc space-y-1 pl-5 marker:text-signal">
            {block.items.map((item, j) => (
              <li key={j}>{renderBold(item, figures)}</li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}

// Same pattern the server cites figures with (app/api/chat.py _MONEY).
const MONEY = /(-?\$[\d,]+(?:\.\d+)?)/g;

function Figure({ text, figures }: { text: string; figures?: FigureSources }) {
  const number = figures?.citations.find((c) => c.text === text)?.source;
  if (!number) return <span className="font-mono text-[0.94em] tabular-nums">{text}</span>;
  const source = figures?.sources[number - 1];
  const mark = (
    <>
      <span className="fig text-ink">{text}</span>
      <sup className="ml-px font-mono text-[10px] text-signal">{number}</sup>
    </>
  );
  if (!source?.query) {
    return (
      <span title={`From source ${number}: ${source?.label ?? ""}`}>
        {mark}
        <span className="sr-only"> (source {number})</span>
      </span>
    );
  }
  const query = source.query;
  return (
    <button
      type="button"
      onClick={() => figures?.onOpen(query)}
      title={`See the transactions behind ${text}`}
      aria-label={`${text}, source ${number}: ${source.label}. See the transactions`}
      className="cursor-pointer rounded-sm hover:bg-signal-wash"
    >
      {mark}
    </button>
  );
}

function renderFigures(text: string, keyPrefix: string, figures?: FigureSources): ReactNode[] {
  return text.split(MONEY).map((part, i) =>
    /^-?\$[\d,]/.test(part) ? (
      <Figure key={`${keyPrefix}-${i}`} text={part} figures={figures} />
    ) : (
      <span key={`${keyPrefix}-${i}`}>{part}</span>
    ),
  );
}

function renderBold(line: string, figures?: FigureSources): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
    chunk.startsWith("**") && chunk.endsWith("**") ? (
      <strong key={j} className="font-semibold">
        {renderFigures(chunk.slice(2, -2), `b${j}`, figures)}
      </strong>
    ) : (
      <span key={j}>{renderFigures(chunk, `t${j}`, figures)}</span>
    )
  );
}
