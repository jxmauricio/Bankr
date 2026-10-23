import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { openSource } from "@/features/source/openSource";
import type { ChartHeadline, ChatSource, SourceQuery, TransactionRecord, ViewLink } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { colors, radius, space } from "@/theme/tokens";
import { Text } from "@/ui";

// The pieces the web app's StreamEntry draws around a reply
// (web/src/pages/HomePage.tsx and web/src/components/ChatChart.tsx).

/** The answer first: the range, one big number, one line of context. */
export function AnswerHeadline({ headline }: { headline: ChartHeadline }) {
  const tone = headline.tone === "pos" ? "positive" : headline.tone === "neg" ? "negative" : "default";
  const sign = headline.tone === "pos" && headline.value > 0 ? "+" : headline.tone === "neg" && headline.value < 0 ? "−" : "";
  return (
    <View style={styles.headline}>
      <Text variant="eyebrow" tone="faint">
        {headline.eyebrow}
      </Text>
      <Text variant="moneyLarge" tone={tone}>
        {sign}
        {formatMoney(Math.abs(headline.value))}
      </Text>
      {headline.detail ? (
        <Text variant="caption" tone="soft">
          {headline.detail}
        </Text>
      ) : null}
    </View>
  );
}

/** The lookup a record came from, so tapping it opens the same rows. */
export function recordQuery(sources: ChatSource[]): SourceQuery | null {
  return [...sources].reverse().find((s) => s.tool === "find_transactions" && s.query)?.query ?? null;
}

/** "Today, Sep 19" for the record card; plain dates otherwise. */
function recordDate(iso: string): string {
  const today = new Date();
  const local = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  return iso === local ? `Today, ${formatDate(iso)}` : formatDate(iso);
}

/** The one record a quick question is about ("did my paycheck come in?"). */
export function RecordCard({ record, query }: { record: TransactionRecord; query: SourceQuery | null }) {
  const name = record.merchant_name ?? record.category ?? "Transaction";
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const incoming = record.amount > 0;
  return (
    <Pressable
      disabled={!query}
      onPress={() => query && openSource(query)}
      style={({ pressed }) => [styles.record, pressed && styles.pressed]}
    >
      <View style={styles.initials}>
        <Text variant="label" tone="accent">
          {initials}
        </Text>
      </View>
      <View style={styles.flex}>
        <Text numberOfLines={1}>{record.category ? `${record.category} · ${name}` : name}</Text>
        <Text variant="citation" tone="faint" numberOfLines={1}>
          {[recordDate(record.date), record.account, record.is_pending ? "Pending" : "Posted"].filter(Boolean).join(" · ")}
        </Text>
      </View>
      <Text variant="money" tone={incoming ? "accent" : "default"}>
        {incoming ? "+" : "−"}
        {formatMoney(Math.abs(record.amount))}
      </Text>
      {query && <Text tone="faint">›</Text>}
    </Pressable>
  );
}

/** An empty search's working: what was looked for, when, and where. */
export function SearchedBox({ source }: { source: ChatSource }) {
  const searched = source.searched!;
  return (
    <View style={styles.searchedWrap}>
      <View style={styles.searched}>
        <Text variant="citation" tone="faint">
          SEARCHED
        </Text>
        <Text variant="caption" tone="soft">
          {searched.what} · {searched.range}
          {searched.accounts.length > 0 && ` · ${searched.accounts.join(", ")}`}
        </Text>
      </View>
      <Text variant="caption" tone="soft">
        If you paid with a card that isn&apos;t linked, it won&apos;t show up here.
      </Text>
    </View>
  );
}

/** "3 sources ▾": the lookups the answer was grounded in, collapsed until asked for. */
export function SourceTrail({ sources }: { sources: ChatSource[] }) {
  const [open, setOpen] = useState(false);
  return (
    <View style={styles.trail}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityHint="Grounded in your real account data via these lookups"
        onPress={() => setOpen((o) => !o)}
        hitSlop={8}
      >
        <Text variant="caption" tone="soft">
          {sources.length} source{sources.length === 1 ? "" : "s"} {open ? "▴" : "▾"}
        </Text>
      </Pressable>
      {open &&
        sources.map((source, i) => (
          <Pressable
            key={i}
            disabled={!source.query}
            onPress={() => source.query && openSource(source.query)}
            style={({ pressed }) => [styles.chip, pressed && styles.pressed]}
          >
            <Text variant="citation" tone="accent">
              {i + 1}
            </Text>
            <Text variant="caption" tone="soft">
              {source.label}
            </Text>
          </Pressable>
        ))}
    </View>
  );
}

/** "See them in Transactions →" and friends: pictures that didn't fit in the answer's one chart. */
export function ViewLinks({ links }: { links: ViewLink[] }) {
  return (
    <View style={styles.trail}>
      {links.map((link, i) => (
        <Pressable
          key={i}
          onPress={() => (link.view === "cash_flow" || !link.query ? openCashFlow() : openSource(link.query))}
          style={({ pressed }) => [styles.outline, pressed && styles.pressed]}
        >
          <Text variant="caption" tone="soft">
            {link.label} →
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

export function OpenInCashFlow() {
  return (
    <Pressable onPress={openCashFlow} style={({ pressed }) => [styles.accentChip, pressed && styles.pressed]}>
      <Text variant="label" tone="accent">
        Open in Cash flow →
      </Text>
    </Pressable>
  );
}

export function openCashFlow() {
  router.navigate("/cash-flow");
}

const styles = StyleSheet.create({
  flex: { flex: 1, gap: 2 },
  pressed: { opacity: 0.6 },
  headline: { gap: 2 },
  record: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.raised,
  },
  initials: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.accentWash,
  },
  searchedWrap: { gap: space.sm },
  searched: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.lineStrong,
  },
  trail: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: space.sm },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    paddingHorizontal: space.md,
    minHeight: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.raised,
  },
  outline: {
    paddingHorizontal: space.lg,
    minHeight: 40,
    justifyContent: "center",
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.lineStrong,
  },
  accentChip: {
    alignSelf: "flex-start",
    paddingHorizontal: space.lg,
    minHeight: 40,
    justifyContent: "center",
    borderRadius: radius.pill,
    backgroundColor: colors.accentWash,
  },
});
