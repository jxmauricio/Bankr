/**
 * Renders the agent's reply as plain conversational text. The system prompt
 * instructs the model never to use markdown, but LLMs slip -- this is a
 * backstop so a stray **bold** renders as bold instead of literal asterisks,
 * not a general-purpose markdown parser.
 */
export function AssistantText({ text }: { text: string }) {
  const paragraphs = text.split(/\n+/).filter(Boolean);

  return (
    <div className="space-y-2">
      {paragraphs.map((line, i) => (
        <p key={i}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
            chunk.startsWith("**") && chunk.endsWith("**") ? (
              <strong key={j} className="font-semibold">
                {chunk.slice(2, -2)}
              </strong>
            ) : (
              <span key={j}>{chunk}</span>
            )
          )}
        </p>
      ))}
    </div>
  );
}
