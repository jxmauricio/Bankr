import { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { makeStyles, useColors } from "@/theme/theme";

const CLOSE = 0.8;
const SETTLE = { duration: 800, easing: Easing.out(Easing.cubic) };

/** Green under the limit, yellow near it, red over. */
export function trackingColor(spent: number, limit: number | null, colors: { positive: string; warn: string; negative: string }): string {
  if (limit == null || limit <= 0) return colors.positive;
  if (spent > limit) return colors.negative;
  if (spent / limit >= CLOSE) return colors.warn;
  return colors.positive;
}

/**
 * Spent fills the bar. The cap is a tick through it: at the right when under,
 * sliding left as you go over (double the cap → tick in the middle).
 */
export function TrackingBar({ spent, limit }: { spent: number; limit: number }) {
  const styles = useStyles();
  const colors = useColors();
  const scale = Math.max(spent, limit, 0.01);
  const fillTo = Math.min(1, spent / scale);
  const tickAt = Math.min(1, limit / scale);
  const color = trackingColor(spent, limit, colors);

  const fill = useSharedValue(0);
  const tick = useSharedValue(tickAt);

  useEffect(() => {
    fill.set(0);
    fill.set(withTiming(fillTo, SETTLE));
    tick.set(withTiming(tickAt, SETTLE));
  }, [fill, fillTo, tick, tickAt]);

  const bar = useAnimatedStyle(() => ({ width: `${fill.get() * 100}%` }));
  const marker = useAnimatedStyle(() => ({ left: `${tick.get() * 100}%` }));

  return (
    <View style={styles.wrap}>
      <View style={styles.track}>
        <Animated.View style={[styles.fill, { backgroundColor: color }, bar]} />
      </View>
      <Animated.View style={[styles.tick, marker]} />
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    wrap: { height: 18, justifyContent: "center" },
    track: {
      height: 10,
      borderRadius: 5,
      backgroundColor: colors.line,
      overflow: "hidden",
    },
    fill: { height: "100%", borderRadius: 5 },
    tick: {
      position: "absolute",
      top: 0,
      bottom: 0,
      width: 2,
      marginLeft: -1,
      borderRadius: 1,
      backgroundColor: colors.ink,
    },
  })
);
