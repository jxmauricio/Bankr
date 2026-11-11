import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withDelay, withTiming } from "react-native-reanimated";
import { makeStyles } from "@/theme/theme";

const SIZE = 36;
const LINE = 40;
const COPIES = 3;
const STRIP = 10 * COPIES;
const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

type Part = { kind: "digit"; digit: number; place: number } | { kind: "mark"; ch: string };

/** Breaks a dollar amount into a leading mark, grouped digits, and cents. */
function partsOf(amount: number): Part[] {
  const sign = amount < 0 ? "-" : "";
  const cents = Math.round(Math.abs(amount) * 100);
  const whole = Math.floor(cents / 100).toLocaleString("en-US");
  const frac = (cents % 100).toString().padStart(2, "0");
  const parts: Part[] = [];
  if (sign) parts.push({ kind: "mark", ch: "-" });
  parts.push({ kind: "mark", ch: "$" });
  for (const ch of whole) {
    if (ch === ",") parts.push({ kind: "mark", ch: "," });
    else parts.push({ kind: "digit", digit: Number(ch), place: 0 });
  }
  parts.push({ kind: "mark", ch: "." });
  parts.push({ kind: "digit", digit: Number(frac[0]), place: 0 });
  parts.push({ kind: "digit", digit: Number(frac[1]), place: 0 });
  let place = 0;
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.kind === "digit") p.place = place++;
  }
  return parts;
}

/**
 * A cash-register readout: each digit rolls on its own reel, smaller
 * places spinning farther, so the figure ticks into place instead of
 * interpolating as one number.
 */
export function RegisterAmount({ value }: { value: number }) {
  const styles = useStyles();
  return (
    <View style={styles.row} accessibilityElementsHidden>
      {partsOf(value).map((part, i) =>
        part.kind === "mark" ? (
          <Mark key={`m-${i}-${part.ch}`} ch={part.ch} />
        ) : (
          <Reel key={`d-${part.place}`} digit={part.digit} place={part.place} />
        )
      )}
    </View>
  );
}

function Mark({ ch }: { ch: string }) {
  const styles = useStyles();
  return <Animated.Text style={[styles.glyph, ch === "," || ch === "." ? styles.mark : null]}>{ch}</Animated.Text>;
}

function Reel({ digit, place }: { digit: number; place: number }) {
  const styles = useStyles();
  const y = useSharedValue(0);
  const prev = useRef<number | null>(null);
  const extra = place <= 2 ? 2 : place <= 4 ? 1 : 0;
  const duration = 700 + Math.min(place, 6) * 90;
  const delay = Math.min(place, 5) * 35;

  useEffect(() => {
    const from = prev.current;
    prev.current = digit;
    if (from === null) {
      y.set(0);
      const target = -(extra * 10 + digit) * LINE;
      y.set(
        withDelay(
          delay,
          withTiming(target, { duration, easing: Easing.out(Easing.cubic) }, (done) => {
            if (done) y.set(-digit * LINE);
          })
        )
      );
      return;
    }
    if (from === digit) return;
    const forward = (digit - from + 10) % 10;
    const backward = (from - digit + 10) % 10;
    const steps = forward <= backward ? forward : -backward;
    y.set(-from * LINE);
    y.set(
      withTiming(-(from + steps) * LINE, { duration: 480, easing: Easing.out(Easing.cubic) }, (done) => {
        if (done) y.set(-digit * LINE);
      })
    );
  }, [digit, delay, duration, extra, y]);

  const slide = useAnimatedStyle(() => ({ top: y.get() }));
  const strip = Array.from({ length: STRIP }, (_, i) => DIGITS[i % 10]);

  return (
    <View style={styles.reel} collapsable={false}>
      {/* Sizes the reel; the strip is absolutely positioned over it. */}
      <Animated.Text style={[styles.glyph, styles.sizer]}>8</Animated.Text>
      <Animated.View style={[styles.strip, slide]}>
        {strip.map((n, i) => (
          <View key={i} style={styles.cell}>
            <Animated.Text style={styles.glyph}>{n}</Animated.Text>
          </View>
        ))}
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", justifyContent: "center", height: LINE, overflow: "hidden", borderRadius: 1 },
    reel: { height: LINE, overflow: "hidden", position: "relative", borderRadius: 1 },
    strip: { position: "absolute", top: 0, left: 0, right: 0 },
    sizer: { opacity: 0 },
    cell: { height: LINE, justifyContent: "center", alignItems: "center" },
    glyph: {
      fontSize: SIZE,
      lineHeight: SIZE,
      fontWeight: "700",
      letterSpacing: -1,
      fontVariant: ["tabular-nums"],
      includeFontPadding: false,
      color: colors.ink,
      textAlign: "center",
    },
    mark: { paddingHorizontal: 1, height: LINE, lineHeight: LINE },
  })
);
