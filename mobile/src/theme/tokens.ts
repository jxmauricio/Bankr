/**
 * Every visual value the app uses. Screens never hardcode a color, size or
 * font: they go through these tokens (usually via the primitives in src/ui),
 * so the coming redesign is a change to this file and src/ui, not to screens.
 *
 * The dark palette is the web app's night mode ([data-theme="dark"] in
 * web/src/index.css). The light palette is the "Light mode" row of the
 * Bankr iOS Redesign canvas (https://claude.ai/artifact/LMSyVZe6cymbvqQN6D2HZD).
 *
 * Colors follow the system appearance: read them with useColors() or
 * makeStyles() from ./theme, never from a palette directly.
 */
import type { TextStyle } from "react-native";

/** Night: the web app's navy surfaces and money green ([data-theme="dark"] in web/src/index.css). */
export const darkColors = {
  bg: "#0B1426",
  surface: "#111C33",
  raised: "#18243F",
  line: "#1D2A47",
  lineStrong: "#26365A",

  ink: "#F2F5FA",
  inkSoft: "#9AA8C4",
  inkFaint: "#8391AF",

  accent: "#2DD48A",
  accentStrong: "#5EE4A8",
  accentWash: "rgba(45, 212, 138, 0.12)",
  accentBorder: "rgba(45, 212, 138, 0.35)",
  /** Text on an accent fill. */
  onAccent: "#0B1426",
  /** The user's own chat bubbles. */
  userBubble: "#0D7A54",

  /** Money going out, in charts. */
  spend: "#B79CFF",
  positive: "#2DD48A",
  positiveWash: "rgba(45, 212, 138, 0.12)",
  negative: "#FF4D4F",
  negativeWash: "rgba(255, 77, 79, 0.12)",
  warn: "#F5A54A",
  warnWash: "rgba(245, 165, 74, 0.1)",
  scrim: "rgba(4, 9, 20, 0.72)",
  /** Behind a label drawn over a chart, so it reads against any fill. */
  chartLabel: "rgba(4, 9, 20, 0.72)",
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
 * The system font: San Francisco on iOS, Roboto on Android (the Bankr iOS
 * Redesign canvas), so there are no font files to load. Figures use tabular
 * digits so amounts line up in columns.
 */
const figures: TextStyle = { fontVariant: ["tabular-nums"] };

/** Named text styles. Add a variant here rather than styling Text inline. */
export const type = {
  display: { fontSize: 32, fontWeight: "700", letterSpacing: -0.8, lineHeight: 38 },
  title: { fontSize: 22, fontWeight: "700", letterSpacing: -0.5 },
  heading: { fontSize: 17, fontWeight: "600" },
  body: { fontSize: 15, fontWeight: "400", lineHeight: 22 },
  label: { fontSize: 15, fontWeight: "500" },
  caption: { fontSize: 13, fontWeight: "400" },
  /** Secondary lines under a row's title: category, date, account. */
  meta: { fontSize: 13, fontWeight: "400" },
  /** Tab bar labels. */
  tab: { fontSize: 15, fontWeight: "600" },
  /** The app's name, centered in the top bar. */
  brand: { fontSize: 26, fontWeight: "700", letterSpacing: -0.6 },
  /** Uppercase label over a group of cards or rows ("ASK BANKR", "TODAY"). */
  section: { fontSize: 12, fontWeight: "600", letterSpacing: 0.8, textTransform: "uppercase" },
  /** Bold inside a chat answer: the key number. */
  strong: { fontSize: 15, fontWeight: "600", lineHeight: 22 },
  /** Small uppercase label over a headline figure ("OCT 1–16 · FOOD"). */
  eyebrow: { fontSize: 11, fontWeight: "600", letterSpacing: 0.8, textTransform: "uppercase" },
  /** The source number next to a checked figure in a chat answer. */
  citation: { ...figures, fontSize: 10, fontWeight: "600" },
  /** Money always reads as exact figures. */
  money: { ...figures, fontSize: 15, fontWeight: "600" },
  /** Figures in summaries and day headers. */
  moneySmall: { ...figures, fontSize: 13, fontWeight: "500" },
  moneyLarge: { ...figures, fontSize: 34, fontWeight: "700", letterSpacing: -1 },
  /** A figure that isn't money, in a tile ("37%", "4.2 mo"). */
  figure: { ...figures, fontSize: 26, fontWeight: "700", letterSpacing: -0.6 },
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
