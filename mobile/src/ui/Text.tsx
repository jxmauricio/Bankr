import { Text as RNText, type TextProps as RNTextProps } from "react-native";
import { tones, type Tone, type TypeVariant, type as typeScale } from "@/theme/tokens";

export interface TextProps extends RNTextProps {
  variant?: TypeVariant;
  tone?: Tone;
  align?: "left" | "center" | "right";
}

export function Text({ variant = "body", tone = "default", align, style, ...rest }: TextProps) {
  return <RNText style={[typeScale[variant], { color: tones[tone], textAlign: align }, style]} {...rest} />;
}
