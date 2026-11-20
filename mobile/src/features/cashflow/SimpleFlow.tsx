import { Pressable, StyleSheet, View } from "react-native";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import type { CashFlowBreakdown } from "@/lib/api";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "@/ui";
import { whole, type FlowTarget } from "./flow";

const TOP = 4;

/**
 * Home flow: income on the left, destinations branching off a spine.
 * The full Sankey is on the visuals page.
 */
export function SimpleFlow({
  flow,
  onPick,
}: {
  flow: CashFlowBreakdown;
  onPick: (target: FlowTarget) => void;
}) {
  const styles = useStyles();
  const colors = useColors();
  const incoming = flow.income;
  const leftover = incoming - flow.spending;
  const head = flow.categories.slice(0, TOP);
  const rest = flow.categories.slice(TOP);
  const nodes: { name: string; amount: number; color: string; target: FlowTarget | null }[] = head.map((c) => ({
    name: c.name,
    amount: c.amount,
    color: hasCategoryColor(c.name) ? colorForCategory(c.name) : colors.spend,
    target: { category: c.name, query: "" },
  }));
  if (rest.length) {
    nodes.push({
      name: "Other",
      amount: rest.reduce((s, c) => s + c.amount, 0),
      color: colors.inkFaint,
      target: null,
    });
  }
  if (leftover > 0) {
    nodes.push({
      name: "Left over",
      amount: leftover,
      color: colors.positive,
      target: null,
    });
  }

  return (
    <View style={styles.row}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`In, ${whole(incoming)}`}
        onPress={() => onPick({ category: "Income", query: "" })}
        style={({ pressed }) => [styles.source, pressed && styles.pressed]}
      >
        <Text variant="caption" tone="faint">
          In
        </Text>
        <Text variant="money" tone="accent">
          {whole(incoming)}
        </Text>
      </Pressable>
      <View style={styles.tree}>
        <View style={styles.spine} />
        <View style={styles.dests}>
          {nodes.map((n) => {
            const row = (
              <View style={styles.dest}>
                <View style={styles.branch} />
                <View style={[styles.swatch, { backgroundColor: n.color }]} />
                <Text numberOfLines={1} style={styles.flex}>
                  {n.name}
                </Text>
                <Text variant="moneySmall">{whole(n.amount)}</Text>
              </View>
            );
            if (!n.target) return <View key={n.name}>{row}</View>;
            return (
              <Pressable key={n.name} accessibilityRole="button" onPress={() => onPick(n.target!)} style={({ pressed }) => pressed && styles.pressed}>
                {row}
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 168 },
    source: { width: 80, gap: 2 },
    tree: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "stretch" },
    spine: { width: 2, backgroundColor: colors.lineStrong },
    dests: { flex: 1, minWidth: 0, justifyContent: "space-evenly" },
    dest: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 28 },
    branch: { width: 12, height: 2, backgroundColor: colors.lineStrong, marginLeft: -1 },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    flex: { flex: 1, minWidth: 0 },
    pressed: { opacity: 0.7 },
  })
);
