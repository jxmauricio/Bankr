import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { BankText } from "@/features/bank/BankLogos";
import { openSource } from "@/features/source/openSource";
import type { ChatSource, Citation } from "@/lib/api";
import { space } from "@/theme/tokens";
import { Text } from "@/ui";

/**
 * Renders the agent's reply with the same rules as the web app's
 * AssistantText (web/src/components/AssistantText.tsx). The system prompt
 * allows exactly two pieces of markup: **bold** for the key number and "- "
 * bullet lines for breakdowns, comparisons and transactions. Those two render;
 * everything else is plain text. It is not a general-purpose markdown parser.
 *
 * Dollar figures read in the money face. A figure the server matched to a
 * tool result (ChatResponse.citations) carries its source number, so the
 * number only ever means "checked"; tapping it lists the transactions behind
 * it. Connected banks' names get their logo.
 */
export function AssistantText({
  text,
  citations = [],
  sources = [],
}: {
  text: string;
  citations?: Citation[];
  sources?: ChatSource[];
}) {
  const figures = { citations, sources };
  const lines = text.split(/\n+/).filter((line) => line.trim());

  // Group consecutive "- " lines into one list; everything else is a paragraph.
  const blocks: ({ kind: "p"; line: string } | { kind: "ul"; items: string[] })[] = [];
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
    <View style={styles.blocks}>
      {blocks.map((block, i) =>
        block.kind === "p" ? (
          <Text key={i}>{renderBold(block.line, figures)}</Text>
        ) : (
          <View key={i} style={styles.list}>
            {block.items.map((item, j) => (
              <View key={j} style={styles.item}>
                <Text tone="accent" accessibilityElementsHidden importantForAccessibility="no">
                  •
                </Text>
                <Text style={styles.itemText}>{renderBold(item, figures)}</Text>
              </View>
            ))}
          </View>
        )
      )}
    </View>
  );
}

// Same pattern the server cites figures with (app/api/chat.py _MONEY).
const MONEY = /(-?\$[\d,]+(?:\.\d+)?)/g;

interface Figures {
  citations: Citation[];
  sources: ChatSource[];
}

function Figure({ text, figures }: { text: string; figures: Figures }) {
  const number = figures.citations.find((c) => c.text === text)?.source;
  const source = number ? figures.sources[number - 1] : undefined;
  const query = source?.query;
  return (
    <Text
      variant="money"
      onPress={query ? () => openSource(query) : undefined}
      style={query ? styles.tappable : undefined}
      accessibilityRole={query ? "link" : undefined}
      accessibilityHint={query ? "Shows the transactions behind this number" : undefined}
    >
      {text}
      {number ? (
        <Text variant="citation" tone="accent" accessibilityLabel={` (source ${number})`}>
          {` ${number}`}
        </Text>
      ) : null}
    </Text>
  );
}

function renderFigures(text: string, keyPrefix: string, figures: Figures): ReactNode[] {
  return text
    .split(MONEY)
    .filter(Boolean)
    .map((part, i) =>
      /^-?\$[\d,]/.test(part) ? (
        <Figure key={`${keyPrefix}-${i}`} text={part} figures={figures} />
      ) : (
        <BankText key={`${keyPrefix}-${i}`} text={part} />
      )
    );
}

function renderBold(line: string, figures: Figures): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
    chunk.startsWith("**") && chunk.endsWith("**") ? (
      <Text key={j} variant="strong">
        {renderFigures(chunk.slice(2, -2), `b${j}`, figures)}
      </Text>
    ) : (
      renderFigures(chunk, `t${j}`, figures)
    )
  );
}

const styles = StyleSheet.create({
  blocks: { gap: space.sm },
  list: { gap: space.xs },
  item: { flexDirection: "row", gap: space.sm },
  itemText: { flex: 1 },
  // A checked figure is a link to its transactions.
  tappable: { textDecorationLine: "underline", textDecorationStyle: "dotted" },
});
