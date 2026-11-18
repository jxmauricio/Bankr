import { useRef, useState } from "react";
import { Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { ScrollView } from "react-native-gesture-handler";
import { whole } from "@/features/cashflow/flow";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Card, FillBar, Text } from "@/ui";
import type { BudgetLine } from "./insights";

type Pitch = { title: string; body: string; cta: string };
type GoalSketch = { name: string; target: number; saved: number };
type Worth = { assets: number; cash: number; emergency: number; invested: number; owed: number; net: number };
type Budget = {
  income: number;
  budgeted: number;
  left: number;
  lines: BudgetLine[];
};

export function RecapCarousel({
  budget,
  goals,
  worth,
  pitch,
  onContinue,
}: {
  budget: Budget | null;
  goals: GoalSketch[];
  worth: Worth | null;
  pitch: Pitch;
  onContinue: () => void;
}) {
  const styles = useStyles();
  const pager = useRef<ScrollView>(null);
  const { width: windowWidth } = useWindowDimensions();
  const [page, setPage] = useState(0);
  const [width, setWidth] = useState(0);
  const pageW = width || windowWidth;
  const last = 3;

  function go(index: number) {
    const next = Math.max(0, Math.min(last, index));
    setPage(next);
    pager.current?.scrollTo({ x: next * pageW, animated: true });
  }

  return (
    <View style={styles.fill}>
      <View style={styles.dots} accessibilityLabel={`Recap ${page + 1} of 4`}>
        {[0, 1, 2, 3].map((i) => (
          <Pressable key={i} onPress={() => go(i)} hitSlop={8} accessibilityRole="tab" accessibilityState={{ selected: i === page }}>
            <View style={[styles.dot, i === page && styles.dotOn]} />
          </Pressable>
        ))}
      </View>
      <View style={styles.pager} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {pageW > 0 ? (
          <ScrollView
            ref={pager}
            horizontal
            pagingEnabled
            nestedScrollEnabled
            showsHorizontalScrollIndicator={false}
            onScroll={(e) => {
              const next = Math.round(e.nativeEvent.contentOffset.x / pageW);
              if (next !== page) setPage(next);
            }}
            scrollEventThrottle={16}
          >
            <View style={{ width: pageW }}>{budget ? <BudgetSketch budget={budget} /> : <EmptyNote text="We'll sketch a month once pay is in." />}</View>
            <View style={{ width: pageW }}>
              <GoalsSketch goals={goals} />
            </View>
            <View style={{ width: pageW }}>{worth ? <NetSketch worth={worth} /> : <EmptyNote text="Net worth shows up after investments and debts." />}</View>
            <View style={{ width: pageW }}>
              <View style={styles.cta}>
                <Text variant="display">{pitch.title}</Text>
                <Text tone="soft">{pitch.body}</Text>
                <Text variant="heading">{pitch.cta}</Text>
              </View>
            </View>
          </ScrollView>
        ) : null}
      </View>
      <View style={styles.footer}>
        <Button
          label="Continue"
          onPress={() => {
            if (page < last) go(page + 1);
            else onContinue();
          }}
        />
      </View>
    </View>
  );
}

function BudgetSketch({ budget }: { budget: Budget }) {
  const styles = useStyles();
  const colors = useColors();
  const left = budget.left;
  return (
    <Card>
      <Text variant="sectionTitle">Monthly budget</Text>
      <Text variant="moneyLarge" tone={left < 0 ? "negative" : "positive"} align="center">
        {whole(left)}
      </Text>
      <Text variant="caption" tone="soft" align="center">
        Money left
      </Text>
      <View style={styles.stats}>
        <View style={styles.stat}>
          <Text variant="eyebrow" tone="soft" align="center">
            Coming in
          </Text>
          <Text variant="money" align="center">
            {whole(budget.income)}
          </Text>
        </View>
        <View style={styles.stat}>
          <Text variant="eyebrow" tone="soft" align="center">
            Budgeted
          </Text>
          <Text variant="money" align="center">
            {whole(budget.budgeted)}
          </Text>
        </View>
        <View style={styles.stat}>
          <Text variant="eyebrow" tone="soft" align="center">
            Saved
          </Text>
          <Text variant="money" tone={left < 0 ? "negative" : "default"} align="center">
            {whole(Math.max(0, left))}
          </Text>
        </View>
      </View>
      {budget.lines.map((line) => {
        const color = hasCategoryColor(line.colorKey) ? colorForCategory(line.colorKey) : colors.positive;
        const fraction = budget.income > 0 ? Math.min(1, line.amount / budget.income) : 0;
        return (
          <View key={line.name} style={styles.line}>
            <View style={styles.lineTop}>
              <View style={[styles.swatch, { backgroundColor: color }]} />
              <Text variant="strong" numberOfLines={1} style={styles.flex}>
                {line.name}
              </Text>
              <Text variant="moneySmall" tone="soft">
                {whole(line.amount)}
              </Text>
            </View>
            <FillBar fraction={fraction} color={color} />
          </View>
        );
      })}
      <Text variant="caption" tone="soft">
        A sketch from what you told us — not a verdict.
      </Text>
    </Card>
  );
}

function GoalsSketch({ goals }: { goals: GoalSketch[] }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <Card>
      <Text variant="sectionTitle">Goals</Text>
      {goals.length === 0 ? (
        <Text tone="soft">We'll pick a first target once we see the month.</Text>
      ) : (
        goals.map((g) => (
          <View key={g.name} style={styles.goal}>
            <View style={styles.lineTop}>
              <Text variant="strong" numberOfLines={1} style={styles.flex}>
                {g.name}
              </Text>
              <Text variant="moneySmall" tone="soft">
                {g.target > 0 ? `${whole(g.saved)} of ${whole(g.target)}` : g.saved > 0 ? whole(g.saved) : "No target yet"}
              </Text>
            </View>
            <FillBar fraction={g.target > 0 ? Math.min(1, g.saved / g.target) : 0} color={colors.positive} />
            <Text variant="caption" tone="soft">
              {g.target > 0 && g.saved >= g.target ? "Reached" : g.saved > 0 ? "Already underway" : "Starting from here"}
            </Text>
          </View>
        ))
      )}
    </Card>
  );
}

function NetSketch({ worth }: { worth: Worth }) {
  return (
    <Card>
      <Text variant="sectionTitle">Estimated net worth</Text>
      <Text variant="moneyLarge" tone={worth.net < 0 ? "negative" : "positive"} align="center">
        {whole(worth.net)}
      </Text>
      <Text tone="soft" align="center">
        {worth.cash ? `${whole(worth.cash)} cash` : "No cash listed"}
      </Text>
      <Text tone="soft" align="center">
        {worth.emergency ? `${whole(worth.emergency)} emergency fund` : "No emergency fund listed"}
      </Text>
      <Text tone="soft" align="center">
        {worth.invested ? `${whole(worth.invested)} invested` : "No investments listed"}
      </Text>
      <Text tone="soft" align="center">
        {worth.owed ? `${whole(worth.owed)} still owed` : "No debt listed"}
      </Text>
      <Text variant="caption" tone="soft" align="center">
        Linking a bank will replace this guess with the real number.
      </Text>
    </Card>
  );
}

function EmptyNote({ text }: { text: string }) {
  return (
    <Card>
      <Text tone="soft">{text}</Text>
    </Card>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    fill: { flex: 1 },
    pager: { flex: 1 },
    footer: { gap: space.sm, marginTop: space.md },
    dots: { flexDirection: "row", gap: space.sm, justifyContent: "center", marginBottom: space.md },
    dot: { width: 6, height: 6, backgroundColor: colors.lineStrong },
    dotOn: { backgroundColor: colors.accent },
    stats: { flexDirection: "row", gap: space.md, paddingTop: space.sm },
    stat: { flex: 1, gap: 2, alignItems: "center" },
    line: { gap: space.sm, paddingTop: space.sm },
    lineTop: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    flex: { flex: 1, minWidth: 0 },
    goal: { gap: space.sm, paddingTop: space.sm },
    cta: { flex: 1, justifyContent: "center", gap: space.md, paddingHorizontal: space.sm },
  })
);
