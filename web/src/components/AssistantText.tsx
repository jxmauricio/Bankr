import type { ReactNode } from "react";

/**
 * Renders the agent's reply. The system prompt allows exactly two pieces of
 * markup: **bold** for the key number and "- " bullet lines for breakdowns,
 * comparisons and transactions. This renders those two and treats everything
 * else as plain text -- it is not a general-purpose markdown parser.
 */
export function AssistantText({ text }: { text: string }) {
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
          <p key={i}>{renderBold(block.line)}</p>
        ) : (
          <ul key={i} className="list-disc space-y-0.5 pl-5 tabular-nums">
            {block.items.map((item, j) => (
              <li key={j}>{renderBold(item)}</li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}

function renderBold(line: string): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
    chunk.startsWith("**") && chunk.endsWith("**") ? (
      <strong key={j} className="font-semibold">
        {chunk.slice(2, -2)}
      </strong>
    ) : (
      <span key={j}>{chunk}</span>
    )
  );
}
