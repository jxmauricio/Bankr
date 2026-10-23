/**
 * Every visual value the app uses. Screens never hardcode a color, size or
 * font: they go through these tokens (usually via the primitives in src/ui),
 * so the coming redesign is a change to this file and src/ui, not to screens.
 *
 * Values follow the "Bankr Mobile" design in Claude Design
 * (https://claude.ai/artifact/PLuTHqLnEE4qZ9W8Mhodxt), which shares its
 * dark palette with the web app's @theme (web/src/index.css). The light
 * palette is the "Light mode" row of the Bankr iOS Redesign canvas
 * (https://claude.ai/artifact/LMSyVZe6cymbvqQN6D2HZD).
 *
 * Colors follow the system appearance: read them with useColors() or
 * makeStyles() from ./theme, never from a palette directly.
 */
import type { TextStyle } from "react-native";

export const darkColors = {
  bg: "#0B0D10",
  surface: "#12151A",
  raised: "#191D24",
  line: "#222731",
  lineStrong: "#323946",

  ink: "#E6EAF0",
  inkSoft: "#A3ABBA",
  inkFaint: "#7B8296",

  accent: "#3ED1BF",
  accentStrong: "#7FE6D9",
  accentWash: "rgba(62, 209, 191, 0.08)",
  accentBorder: "rgba(62, 209, 191, 0.35)",
  /** Text on an accent fill. */
  onAccent: "#0B0D10",
  /** The user's own chat bubbles. */
  userBubble: "#0F6E6A",

  /** Money going out, in charts. */
  spend: "#B79CFF",
  positive: "#4FD18B",
  positiveWash: "rgba(79, 209, 139, 0.12)",
  negative: "#FF7A6B",
  negativeWash: "rgba(255, 122, 107, 0.1)",
  warn: "#F5A54A",
  warnWash: "rgba(245, 165, 74, 0.1)",
  scrim: "rgba(5, 6, 8, 0.72)",
  /** Behind a label drawn over a chart, so it reads against any fill. */
  chartLabel: "rgba(5, 6, 8, 0.72)",
  /** Behind bank logos, which are drawn for a light background. */
  logoBacking: "#FFFFFF",
};

export type Colors = typeof darkColors;

/** Soft gray-white page, white cards, navy ink and a blue accent. */
export const lightColors: Colors = {
  bg: "#F3F5F9",
  surface: "#FFFFFF",
  raised: "#E9EDF3",
  line: "#E2E7EF",
  lineStrong: "#D3DAE5",

  ink: "#0E1A2B",
  inkSoft: "#5A6678",
  inkFaint: "#667085",

  accent: "#2F6FE0",
  accentStrong: "#1D4ED8",
  accentWash: "rgba(47, 111, 224, 0.08)",
  accentBorder: "rgba(47, 111, 224, 0.35)",
  onAccent: "#FFFFFF",
  userBubble: "#DCE7FB",

  spend: "#7C5CE0",
  positive: "#15803D",
  positiveWash: "rgba(21, 128, 61, 0.1)",
  negative: "#C93A2B",
  negativeWash: "rgba(201, 58, 43, 0.08)",
  warn: "#B45309",
  warnWash: "rgba(180, 83, 9, 0.1)",
  scrim: "rgba(16, 24, 40, 0.4)",
  chartLabel: "rgba(255, 255, 255, 0.88)",
  logoBacking: "#FFFFFF",
};

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 14,
  lg: 20,
  pill: 999,
} as const;

/**
 * Space Grotesk for words, JetBrains Mono for every figure (the Claude Design
 * mockup, "Bankr Mobile"). Each weight is its own family on native, so text
 * styles name a family and never set fontWeight. Loaded in app/_layout.tsx.
 */
export const fonts = {
  regular: "SpaceGrotesk_400Regular",
  medium: "SpaceGrotesk_500Medium",
  semibold: "SpaceGrotesk_600SemiBold",
  mono: "JetBrainsMono_400Regular",
  monoMedium: "JetBrainsMono_500Medium",
} as const;

/** Named text styles. Add a variant here rather than styling Text inline. */
export const type = {
  display: { fontSize: 32, fontFamily: fonts.semibold, letterSpacing: -0.6, lineHeight: 38 },
  title: { fontSize: 22, fontFamily: fonts.semibold, letterSpacing: -0.4 },
  heading: { fontSize: 17, fontFamily: fonts.semibold },
  body: { fontSize: 15, fontFamily: fonts.regular, lineHeight: 22 },
  label: { fontSize: 14, fontFamily: fonts.medium },
  caption: { fontSize: 13, fontFamily: fonts.regular },
  /** Secondary lines under a row's title: category, date, account. */
  meta: { fontSize: 12, fontFamily: fonts.regular },
  /** Tab bar labels. */
  tab: { fontSize: 15, fontFamily: fonts.medium },
  /** The app's name, centered in the top bar. */
  brand: { fontSize: 26, fontFamily: fonts.semibold, letterSpacing: -0.6 },
  /** Uppercase label over a group of cards or rows ("ASK BANKR", "TODAY"). */
  section: { fontSize: 12, fontFamily: fonts.semibold, letterSpacing: 0.8, textTransform: "uppercase" },
  /** Bold inside a chat answer: the key number. */
  strong: { fontSize: 15, fontFamily: fonts.semibold, lineHeight: 22 },
  /** Small uppercase label over a headline figure ("OCT 1–16 · FOOD"). */
  eyebrow: { fontSize: 11, fontFamily: fonts.mono, letterSpacing: 1.1, textTransform: "uppercase" },
  /** The source number next to a checked figure in a chat answer. */
  citation: { fontSize: 10, fontFamily: fonts.monoMedium },
  /** Money always reads as exact figures. */
  money: { fontSize: 15, fontFamily: fonts.monoMedium, fontVariant: ["tabular-nums"] },
  /** Figures in summaries and day headers. */
  moneySmall: { fontSize: 13, fontFamily: fonts.mono, fontVariant: ["tabular-nums"] },
  moneyLarge: { fontSize: 32, fontFamily: fonts.monoMedium, letterSpacing: -1.3, fontVariant: ["tabular-nums"] },
} satisfies Record<string, TextStyle>;

export type TypeVariant = keyof typeof type;

/** Semantic text colors, so screens say what a value means, not what color it is. */
export function tones(colors: Colors) {
  return {
    default: colors.ink,
    soft: colors.inkSoft,
    faint: colors.inkFaint,
    accent: colors.accent,
    positive: colors.positive,
    spend: colors.spend,
    negative: colors.negative,
    warn: colors.warn,
    onAccent: colors.onAccent,
  };
}

export type Tone = keyof ReturnType<typeof tones>;
