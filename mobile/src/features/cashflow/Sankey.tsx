import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import Svg, { G, Path, Rect } from "react-native-svg";
import type { CashFlowBreakdown } from "@/lib/api";
import { radius } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "@/ui";
import { useKindColors, whole, type FlowNode, type FlowTarget } from "./flow";

// Phone geometry, in points. The web version is a fixed 980-wide canvas with
// labels on both outer sides; a phone can't spare that, so left labels sit
// just inside their nodes, over the ribbons, and only the right column keeps
// a label gutter.
const NODE_W = 8;
const GAP_L = 14;
const GAP_R = 10;
/** Room each label needs: name line plus amount line. */
const LABEL_H = 32;
const PAD = 12;

/** Push labels down to keep `gap` between them, then pull the stack back up if it ran past `max`. */
function spread(ys: number[], gap: number, min: number, max: number): number[] {
  const out = [...ys];
  for (let i = 1; i < out.length; i++) out[i] = Math.max(out[i], out[i - 1] + gap);
  const overflow = out.length ? out[out.length - 1] - max : 0;
  if (overflow > 0) {
    out[out.length - 1] -= overflow;
    for (let i = out.length - 2; i >= 0; i--) out[i] = Math.min(out[i], out[i + 1] - gap);
  }
  return out.map((y) => Math.max(y, min));
}

function ribbon(x0: number, a0: number, b0: number, x1: number, a1: number, b1: number) {
  const m = (x0 + x1) / 2;
  return `M${x0},${a0} C${m},${a0} ${m},${a1} ${x1},${a1} L${x1},${b1} C${m},${b1} ${m},${b0} ${x0},${b0} Z`;
}

/**
 * Where the money came from (left) and went (right), through one middle bar.
 * Same layout math as the web Sankey; tap a label to open its transactions,
 * press and hold to highlight its ribbon.
 */
export function Sankey({
  flow,
  left,
  right,
  total,
  onPick,
}: {
  flow: CashFlowBreakdown;
  left: FlowNode[];
  right: FlowNode[];
  total: number;
  onPick: (target: FlowTarget) => void;
}) {
  const styles = useStyles();
  const kindColors = useKindColors();
  const colors = useColors();
  const [width, setWidth] = useState(0);
  const [focus, setFocus] = useState<string | null>(null);

  // Tall enough that the bigger column's labels never have to overlap.
  const H = Math.max(260, Math.max(left.length, right.length) * (LABEL_H + 4));
  const labelW = Math.min(150, width * 0.42);
  const XL = 0;
  const XR = width - labelW - NODE_W - 6;
  const XM = XR * 0.5;

  const k = total > 0 ? (H - GAP_R * Math.max(right.length - 1, 0)) / total : 0;
  const midH = total * k;
  const midY = (H - midH) / 2;

  const rects: { x: number; y: number; h: number; color: string }[] = [];
  const links: { d: string; color: string; name: string }[] = [];
  const labels: { node: FlowNode; side: "left" | "right"; y: number }[] = [];

  const leftH = total * k + GAP_L * Math.max(left.length - 1, 0);
  let y = Math.max((H - leftH) / 2, 0);
  let mIn = midY;
  for (const node of left) {
    const h = node.amount * k;
    rects.push({ x: XL, y, h: Math.max(h, 2), color: kindColors[node.kind] });
    links.push({
      d: ribbon(XL + NODE_W, y, y + h, XM, mIn, mIn + h),
      color: kindColors[node.kind],
      name: node.name,
    });
    labels.push({ node, side: "left", y: y + h / 2 });
    y += h + GAP_L;
    mIn += h;
  }
  rects.push({ x: XM, y: midY, h: midH, color: colors.ink });

  let yr = 0;
  let mOut = midY;
  for (const node of right) {
    const h = node.amount * k;
    rects.push({
      x: XR,
      y: yr,
      h: Math.max(h, 2),
      color: kindColors[node.kind],
    });
    links.push({
      d: ribbon(XM + NODE_W, mOut, mOut + h, XR, yr, yr + h),
      color: kindColors[node.kind],
      name: node.name,
    });
    labels.push({ node, side: "right", y: yr + h / 2 });
    yr += h + GAP_R;
    mOut += h;
  }

  const leftYs = spread(
    labels.filter((l) => l.side === "left").map((l) => l.y),
    LABEL_H,
    LABEL_H / 2,
    H - LABEL_H / 2
  );
  const rightYs = spread(
    labels.filter((l) => l.side === "right").map((l) => l.y),
    LABEL_H,
    LABEL_H / 2,
    H - LABEL_H / 2
  );
  let li = 0;
  let ri = 0;
  for (const l of labels) l.y = l.side === "left" ? leftYs[li++] : rightYs[ri++];

  const pct = (n: number) => `${Math.round((n / total) * 100)}%`;
  const moneyOut = flow.spending + (flow.transfer_out ?? 0) > flow.income + (flow.transfer_in ?? 0);
  const summary = `Cash flow for ${flow.label}: ${whole(flow.income)} income, ${whole(flow.spending)} spending${
    flow.net > 0 ? `, ${whole(flow.net)} left over` : `, ${whole(-flow.net)} more out than in`
  }.`;

  return (
    <View>
      <View style={styles.total}>
        <Text variant="caption">{moneyOut ? "Money out" : "Money in"}</Text>
        <Text variant="money" tone="soft">
          {whole(total)}
        </Text>
      </View>
      <View
        style={{ height: H + PAD * 2 }}
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
        accessible
        accessibilityLabel={summary}
      >
        {width > 0 && (
          <>
            <Svg width={width} height={H + PAD * 2} style={StyleSheet.absoluteFill}>
              <G transform={`translate(0 ${PAD})`}>
                {links.map((l) => (
                  <Path
                    key={`${l.color}-${l.name}`}
                    d={l.d}
                    fill={l.color}
                    opacity={focus ? (focus === l.name ? 0.55 : 0.08) : 0.28}
                  />
                ))}
                {rects.map((r, i) => (
                  <Rect key={i} x={r.x} y={r.y} width={NODE_W} height={r.h} rx={3} fill={r.color} />
                ))}
              </G>
            </Svg>

            {labels.map(({ node, side, y: ly }) => {
              const style =
                side === "left"
                  ? {
                      left: XL + NODE_W + 4,
                      top: ly + PAD - LABEL_H / 2,
                      maxWidth: XM - NODE_W - 12,
                    }
                  : {
                      left: XR + NODE_W + 4,
                      top: ly + PAD - LABEL_H / 2,
                      width: labelW,
                    };
              return (
                <Pressable
                  key={`${side}-${node.kind}-${node.name}`}
                  disabled={!node.target}
                  onPress={() => node.target && onPick(node.target)}
                  onPressIn={() => setFocus(node.name)}
                  onPressOut={() => setFocus(null)}
                  accessibilityRole={node.target ? "button" : "text"}
                  accessibilityLabel={`${node.name}: ${whole(node.amount)}${node.target ? ". Show transactions" : ""}`}
                  style={[styles.label, side === "left" && styles.leftLabel, style]}
                >
                  <Text variant="caption" numberOfLines={1}>
                    {node.name}
                  </Text>
                  <Text variant="citation" style={{ color: kindColors[node.kind] }}>
                    {/* The left column is narrow on a phone, so its labels skip the share. */}
                    {side === "left" ? whole(node.amount) : `${whole(node.amount)} · ${pct(node.amount)}`}
                  </Text>
                </Pressable>
              );
            })}
          </>
        )}
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    total: {
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "baseline",
    },
    label: {
      position: "absolute",
      height: LABEL_H,
      justifyContent: "center",
      paddingHorizontal: 4,
      borderRadius: radius.sm,
    },
    // Left labels sit over the ribbons, so give them a backing to stay readable.
    leftLabel: { backgroundColor: colors.chartLabel },
  })
);
