import { useEffect } from "react";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";
import Svg, { Path } from "react-native-svg";
import { useColors } from "@/theme/theme";

/**
 * A cent mark (a C with a vertical stroke) that turns while something loads,
 * instead of a generic spinner.
 */
export function CentSpinner({ size = 28, color }: { size?: number; color?: string }) {
  const colors = useColors();
  const stroke = color ?? colors.accent;
  const turn = useSharedValue(0);

  useEffect(() => {
    turn.set(withRepeat(withTiming(1, { duration: 1100, easing: Easing.linear }), -1, false));
  }, [turn]);

  const spin = useAnimatedStyle(() => ({ transform: [{ rotate: `${turn.get() * 360}deg` }] }));

  return (
    <Animated.View style={[{ width: size, height: size }, spin]} accessibilityLabel="Loading">
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={1.9} strokeLinecap="round">
        {/* C opening to the right, then the cent bar through it. */}
        <Path d="M17.2 7.2a6.2 6.2 0 1 0 0 9.6" />
        <Path d="M12 3.8v16.4" />
      </Svg>
    </Animated.View>
  );
}
