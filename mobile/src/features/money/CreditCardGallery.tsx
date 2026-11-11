import { useState } from "react";
import { StyleSheet, View, useWindowDimensions, type NativeScrollEvent, type NativeSyntheticEvent } from "react-native";
import { ScrollView } from "react-native-gesture-handler";
import type { AccountBalance } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { FillBar, Text } from "@/ui";
import { useMoney } from "./MoneyContext";

const CARD_RATIO = 1.586;
const PEEK = space.xl;

function lineOf(card: AccountBalance): number | null {
  if (card.credit_limit != null && card.credit_limit > 0) return card.credit_limit;
  if (card.available_balance != null) return card.balance + card.available_balance;
  return null;
}

type Plastic = { bg: string; ink: string; muted: string };

const LOOKS: { match: RegExp; look: Plastic }[] = [
  { match: /wells\s*fargo/i, look: { bg: "#D71E28", ink: "#FFFFFF", muted: "rgba(255,255,255,0.72)" } },
  { match: /chase/i, look: { bg: "#0A4595", ink: "#FFFFFF", muted: "rgba(255,255,255,0.72)" } },
  { match: /american\s*express|\bamex\b/i, look: { bg: "#016FD0", ink: "#FFFFFF", muted: "rgba(255,255,255,0.78)" } },
  { match: /\bciti\b/i, look: { bg: "#003B70", ink: "#FFFFFF", muted: "rgba(255,255,255,0.72)" } },
  { match: /capital\s*one/i, look: { bg: "#004879", ink: "#FFFFFF", muted: "rgba(255,255,255,0.72)" } },
  { match: /discover/i, look: { bg: "#E87722", ink: "#FFFFFF", muted: "rgba(255,255,255,0.85)" } },
  { match: /bank of america|\bbofa\b/i, look: { bg: "#E31837", ink: "#FFFFFF", muted: "rgba(255,255,255,0.78)" } },
  { match: /\busaa\b/i, look: { bg: "#003E7E", ink: "#FFFFFF", muted: "rgba(255,255,255,0.72)" } },
];

function plasticLook(institution: string): Plastic {
  return LOOKS.find((l) => l.match.test(institution))?.look ?? { bg: "#1B2A4A", ink: "#F2F5FA", muted: "rgba(242,245,250,0.7)" };
}

function networkLabel(name: string | null): string | null {
  const n = (name ?? "").toLowerCase();
  if (/\bvisa\b|\bvi\b/.test(n)) return "VISA";
  if (/master\s*card|\bmc\b/.test(n)) return "MASTERCARD";
  if (/amex|american express/.test(n)) return "AMEX";
  if (/discover/.test(n)) return "DISCOVER";
  return null;
}

/**
 * Horizontal gallery of physical-looking cards. The readout under the
 * scroller follows the focused card: owed and credit line.
 */
export function CreditCardGallery() {
  const styles = useStyles();
  const { width } = useWindowDimensions();
  const { netWorth } = useMoney();
  const cards = netWorth.accounts.filter((a) => a.type === "credit");
  const [index, setIndex] = useState(0);
  if (cards.length === 0) return null;

  const cardW = Math.min(340, width - PEEK * 2);
  const cardH = Math.round(cardW / CARD_RATIO);
  const step = cardW + space.md;
  const focused = cards[Math.min(index, cards.length - 1)];

  function onScroll(e: NativeSyntheticEvent<NativeScrollEvent>) {
    const next = Math.round(e.nativeEvent.contentOffset.x / step);
    setIndex(Math.max(0, Math.min(cards.length - 1, next)));
  }

  return (
    <View style={styles.wrap}>
      <Text variant="sectionTitle" style={styles.header}>
        Credit cards
      </Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        decelerationRate="fast"
        snapToInterval={step}
        disableIntervalMomentum
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.scroller}
      >
        {cards.map((card) => (
          <PlasticCard key={`${card.institution}-${card.mask}-${card.name}`} card={card} width={cardW} height={cardH} />
        ))}
      </ScrollView>
      <CardReadout card={focused} count={cards.length} index={index} />
    </View>
  );
}

function PlasticCard({ card, width, height }: { card: AccountBalance; width: number; height: number }) {
  const styles = useStyles();
  const look = plasticLook(card.institution);
  const network = networkLabel(card.name);

  return (
    <View style={[styles.plastic, { width, height, backgroundColor: look.bg }]}>
      <View style={styles.sheen} />
      <View style={styles.plasticTop}>
        <View style={styles.chip} />
        {network ? (
          <Text variant="eyebrow" style={{ color: look.muted }}>
            {network}
          </Text>
        ) : null}
      </View>
      <View style={styles.plasticBottom}>
        <Text variant="heading" numberOfLines={1} style={{ color: look.ink }}>
          {card.institution}
        </Text>
        <Text variant="caption" numberOfLines={1} style={{ color: look.muted }}>
          {card.name ?? "Credit card"}
        </Text>
        <Text variant="money" style={{ color: look.ink }}>
          {card.mask ? `•••• ${card.mask}` : "••••"}
        </Text>
      </View>
    </View>
  );
}

function CardReadout({ card, count, index }: { card: AccountBalance; count: number; index: number }) {
  const styles = useStyles();
  const colors = useColors();
  const limit = lineOf(card);
  const used = limit && limit > 0 ? Math.min(1, card.balance / limit) : null;
  const barColor = used == null ? colors.accent : used > 0.7 ? colors.negative : used > 0.4 ? colors.warn : colors.positive;

  return (
    <View style={styles.readout}>
      {count > 1 && (
        <View style={styles.dots}>
          {Array.from({ length: count }, (_, i) => (
            <View key={i} style={[styles.dot, i === index && styles.dotOn]} />
          ))}
        </View>
      )}
      <View style={styles.readoutRow}>
        <Text variant="heading">{formatMoney(card.balance)} owed</Text>
        {limit != null && (
          <Text variant="caption" tone="soft">
            of {formatMoney(limit)} credit line
          </Text>
        )}
      </View>
      {used != null && (
        <>
          <FillBar fraction={used} color={barColor} height={6} />
          <Text variant="caption" tone="faint">
            {Math.round(used * 100)}% used
          </Text>
        </>
      )}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    wrap: {
      paddingTop: space.xl,
      paddingBottom: space.xl,
      gap: space.md,
      borderBottomWidth: 1,
      borderBottomColor: colors.lineStrong,
    },
    header: { paddingHorizontal: space.lg },
    scroller: { paddingHorizontal: PEEK, gap: space.md, paddingVertical: space.xs },
    plastic: {
      borderRadius: radius.md,
      padding: space.lg,
      justifyContent: "space-between",
      overflow: "hidden",
    },
    sheen: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      height: 44,
      backgroundColor: "rgba(255,255,255,0.1)",
    },
    plasticTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    chip: {
      width: 34,
      height: 24,
      borderRadius: 4,
      backgroundColor: "#E4C36A",
    },
    plasticBottom: { gap: 2 },
    readout: { paddingHorizontal: space.lg, gap: space.sm, paddingBottom: space.md },
    readoutRow: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: space.sm },
    dots: { flexDirection: "row", justifyContent: "center", gap: 6 },
    dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.lineStrong },
    dotOn: { backgroundColor: colors.ink },
  })
);
