import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { ScrollView } from "react-native-gesture-handler";
import { SpendingBars } from "@/features/cashflow/SpendingBars";
import { SpendingPie } from "@/features/cashflow/SpendingPie";
import { SimpleFlow } from "@/features/cashflow/SimpleFlow";
import { useKindColors, sides, whole, type FlowTarget } from "@/features/cashflow/flow";
import { Sankey } from "@/features/cashflow/Sankey";
import type { CashFlowBreakdown } from "@/lib/api";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Icon, Text, type IconName } from "@/ui";

const VIEWS: { id: "pie" | "bar" | "flow"; label: string; icon: IconName }[] = [
  { id: "pie", label: "Pie", icon: "pie" },
  { id: "bar", label: "Bars", icon: "bars" },
  { id: "flow", label: "Flow", icon: "flow" },
];

const HOME_TOP = 5;

/**
 * Three swipeable spending charts. Home is compact: pie first, top 5, icon
 * tabs, names under the pie. The visuals page keeps every category and the list.
 */
export function VisualsPager({
  flow,
  onPick,
  compact = false,
}: {
  flow: CashFlowBreakdown;
  onPick: (target: FlowTarget) => void;
  compact?: boolean;
}) {
  const styles = useStyles();
  const kindColors = useKindColors();
  const colors = useColors();
  const pager = useRef<ScrollView>(null);
  const [page, setPage] = useState(0);
  const [width, setWidth] = useState(0);
  const [open, setOpen] = useState(!compact);
  const data = sides(flow);
  const slices = compact ? flow.categories.slice(0, HOME_TOP) : flow.categories;
  const empty = slices.length === 0;

  useEffect(() => {
    if (width > 0) pager.current?.scrollTo({ x: 0, animated: false });
  }, [width]);

  function go(index: number) {
    setPage(index);
    pager.current?.scrollTo({ x: index * width, animated: true });
  }

  function pickCategory(name: string) {
    onPick({ category: name, query: "" });
  }

  const pages = [
    empty ? (
      <Text key="pie" tone="soft">
        No spending in this period.
      </Text>
    ) : (
      <SpendingPie
        key="pie"
        slices={slices}
        size={compact ? 132 : 156}
        otherColor={colors.inkFaint}
        onPick={pickCategory}
        legend="bottom"
        amounts={!compact}
      />
    ),
    empty ? (
      <Text key="bar" tone="soft">
        No spending in this period.
      </Text>
    ) : (
      <SpendingBars key="bar" slices={slices} onPick={pickCategory} />
    ),
    compact ? (
      <SimpleFlow key="flow" flow={flow} onPick={onPick} />
    ) : (
      <Sankey key="flow" flow={flow} {...data} onPick={onPick} />
    ),
  ];

  const maxRow = Math.max(...data.right.map((r) => r.amount), 1);

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      <View style={styles.dots} accessibilityRole="tablist">
        {VIEWS.map((v, i) => (
          <Pressable
            key={v.id}
            accessibilityRole="tab"
            accessibilityLabel={v.label}
            accessibilityState={{ selected: page === i }}
            onPress={() => go(i)}
            style={styles.dotHit}
          >
            <Icon name={v.icon} color={page === i ? colors.accent : colors.inkFaint} size={20} />
          </Pressable>
        ))}
      </View>
      {width > 0 ? (
        <ScrollView
          ref={pager}
          horizontal
          pagingEnabled
          nestedScrollEnabled
          showsHorizontalScrollIndicator={false}
          style={compact ? { height: page === 1 ? 220 : page === 2 ? 176 : 200 } : undefined}
          onScroll={(e) => {
            if (!width) return;
            const next = Math.round(e.nativeEvent.contentOffset.x / width);
            if (next !== page) setPage(next);
          }}
          scrollEventThrottle={16}
        >
          {pages.map((child, i) => (
            <View key={VIEWS[i].id} style={{ width }}>
              {child}
            </View>
          ))}
        </ScrollView>
      ) : (
        <View style={styles.placeholder} />
      )}

      {compact ? null : (
        <>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: open }}
            onPress={() => setOpen((v) => !v)}
            style={styles.disclose}
          >
            <Text variant="section" tone="soft" style={styles.flex}>
              Where it went
            </Text>
            <Icon name={open ? "chevronDown" : "chevronRight"} color={colors.inkFaint} size={18} />
          </Pressable>
          {open
            ? data.right.map((c, i) => (
                <Pressable
                  key={`${c.kind}-${c.name}`}
                  disabled={!c.target}
                  onPress={() => c.target && onPick(c.target)}
                  style={({ pressed }) => [styles.row, i > 0 && styles.rowLine, pressed && styles.pressed]}
                >
                  <View style={[styles.swatch, { backgroundColor: kindColors[c.kind] }]} />
                  <Text numberOfLines={1} style={styles.flex}>
                    {c.name}
                  </Text>
                  <View style={styles.bar}>
                    <View style={[styles.barFill, { width: `${(c.amount / maxRow) * 100}%`, backgroundColor: kindColors[c.kind] }]} />
                  </View>
                  <Text variant="money" style={styles.amount}>
                    {whole(c.amount)}
                  </Text>
                </Pressable>
              ))
            : null}
        </>
      )}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    placeholder: { height: 180 },
    dots: { flexDirection: "row", justifyContent: "center", gap: space.lg, paddingBottom: space.sm },
    dotHit: { paddingVertical: space.xs, paddingHorizontal: space.sm, minHeight: 36, justifyContent: "center" },
    disclose: { flexDirection: "row", alignItems: "center", minHeight: 40, paddingTop: space.xs },
    flex: { flex: 1, minWidth: 0 },
    row: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44 },
    rowLine: { borderTopColor: colors.line, borderTopWidth: StyleSheet.hairlineWidth },
    pressed: { opacity: 0.6 },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    bar: { width: 60, height: 4, borderRadius: radius.pill, backgroundColor: colors.line, overflow: "hidden" },
    barFill: { height: 4, borderRadius: radius.pill },
    amount: { minWidth: 72, textAlign: "right" },
  })
);
