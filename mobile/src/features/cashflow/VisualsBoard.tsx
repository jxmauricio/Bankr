import { StyleSheet, View } from "react-native";
import { VisualsPager } from "@/features/cashflow/VisualsPager";
import { SpendingPaceChart } from "@/features/cashflow/SpendingPaceChart";
import { sides, type FlowTarget } from "@/features/cashflow/flow";
import { usePeriod } from "@/features/period/PeriodContext";
import type { CashFlowBreakdown, SpendingPace } from "@/lib/api";
import { PERIOD_OPTIONS } from "@/lib/period";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Card, ErrorState, Loading, SegmentedControl, Text } from "@/ui";

/** Period, three swipeable charts, the category list, and this month's pace. */
export function VisualsBoard({
  flow,
  pace,
  onRetry,
  onPick,
}: {
  flow: { status: string; data: CashFlowBreakdown | null; retry: () => void };
  pace: { data: SpendingPace | null };
  onRetry: () => void;
  onPick: (target: FlowTarget) => void;
}) {
  const styles = useStyles();
  const { period, setPeriod } = usePeriod();
  const f = flow.data;
  const data = f ? sides(f) : null;
  const empty = f !== null && f.income === 0 && f.spending === 0 && (f.transfer_in ?? 0) === 0 && (f.transfer_out ?? 0) === 0;

  return (
    <>
      <View style={styles.period}>
        <SegmentedControl label="Period" options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
      </View>
      <Text variant="caption" tone="soft" style={styles.intro}>
        Where your money came from and where it went{f ? ` · ${f.label}` : ""}.
      </Text>

      {flow.status === "error" && !f ? (
        <Card>
          <ErrorState message="Couldn't load spending." onRetry={onRetry} />
        </Card>
      ) : !f || !data ? (
        <Card style={styles.placeholder}>
          <Loading />
        </Card>
      ) : empty ? (
        <Card>
          <Text tone="soft" align="center">
            No income, spending, or transfers in {f.label} yet.
          </Text>
        </Card>
      ) : (
        <View style={styles.pager}>
          <VisualsPager flow={f} onPick={onPick} />
        </View>
      )}

      {pace.data && <SpendingPaceChart pace={pace.data} />}
    </>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    period: { paddingTop: space.sm },
    intro: { paddingHorizontal: space.lg, paddingTop: space.md, paddingBottom: space.sm },
    placeholder: { height: 320 },
    pager: { paddingHorizontal: space.lg },
  })
);
