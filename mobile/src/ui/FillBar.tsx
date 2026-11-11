import { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { makeStyles } from "@/theme/theme";

/** A track whose fill grows from empty to `fraction` (0–1). */
export function FillBar({ fraction, color, height = 8 }: { fraction: number; color: string; height?: number }) {
  const styles = useStyles();
  const width = useSharedValue(0);
  const clamped = Math.min(1, Math.max(0, fraction));

  useEffect(() => {
    width.set(0);
    width.set(withTiming(clamped, { duration: 800, easing: Easing.out(Easing.cubic) }));
  }, [clamped, width]);

  const fill = useAnimatedStyle(() => ({ width: `${width.get() * 100}%` }));

  return (
    <View style={[styles.track, { height, borderRadius: height / 2 }]}>
      <Animated.View style={[styles.fill, { height, backgroundColor: color, borderRadius: height / 2 }, fill]} />
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    track: { backgroundColor: colors.line, overflow: "hidden" },
    fill: { height: "100%" },
  })
);
