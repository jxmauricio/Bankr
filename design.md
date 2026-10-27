# Bankr design

How Bankr looks and why, for the web app (`web/`) and the mobile app
(`mobile/`). The visual direction is calm, card-based and Copilot Money–like:
soft surfaces, hairline borders, large figures, uppercase section labels, and
pill-shaped navigation.

The mockups live on the **Bankr iOS Redesign** canvas
(https://claude.ai/artifact/LMSyVZe6cymbvqQN6D2HZD): the *Mobile* page has
the phone screens in dark and light, and the *Desktop* page has the web screens
with a Light/Dark switch in Tweaks. The code is the source of truth where the
two differ; this file describes the code as it is on `main`.

## Where the values live

| | Web | Mobile |
|---|---|---|
| Colors, radii, shadows | `web/src/index.css` (`@theme` plus `[data-theme="dark"]`) | `mobile/src/theme/tokens.ts` (`lightColors`, `darkColors`) |
| Type | `--font-*` in `web/src/index.css` | `type` in `mobile/src/theme/tokens.ts` |
| Theme switching | `web/src/lib/theme.tsx`, `web/src/components/ThemeToggle.tsx`, and the pre-paint script in `web/index.html` | `mobile/src/theme/theme.ts` (`useColors`, `makeStyles`) and `mobile/src/theme/appearance.ts` |
| Building blocks | Tailwind utilities on the tokens, plus the `.card` class | Primitives in `mobile/src/ui/` |

Rules for both apps:

- **Never hardcode a color.** Use a token, so both themes work. On the web,
  a token in `@theme` must also be set in `[data-theme="dark"]`. On mobile,
  a key in `darkColors` must also be in `lightColors`. The `Colors` type
  enforces that.
- **Say what a value means, not what color it is.** Use `positive`,
  `negative`, `spend` and `warn` rather than "green" or "red", so a palette
  change is a one-file edit.

## Theming

**Web.** Light is the default. The sun/moon button in the top bar switches
to dark, and the choice is saved in `localStorage` under `bankr_theme`. A
small script in `index.html` sets `<html data-theme>` before first paint, so
a dark choice never flashes light. The web app does not follow the system
appearance.

**Mobile.** The app follows the system appearance by default. Settings
(the gear in the top bar) has an **Appearance** control with System, Light
and Dark. The choice applies app-wide through React Native's `Appearance`
override, is saved in SecureStore under `bankr_appearance`, and is applied
before the first frame. Styles are built once per appearance with
`makeStyles((colors) => StyleSheet.create(...))`, and components read colors
with `useColors()`.

## Color

### Web, light (default)

| Token | Value | Use |
|---|---|---|
| `bg` | `#f3f5f8` | Page |
| `surface` | `#ffffff` | Cards, answers, inputs |
| `raised` | `#e8ecf1` | Hover fills, segmented tracks, bar tracks |
| `line` / `line-strong` | `#e2e6ec` / `#cdd4de` | Card borders and dividers / control borders |
| `ink` / `ink-soft` / `ink-faint` | `#12151c` / `#4b5565` / `#7b8494` | Text, secondary text, tertiary text |
| `signal` (accent) | `#00a36c` | Selected tab, primary actions, links |
| `on-signal` | `#ffffff` | Text on a `signal` fill |
| `user` / `on-user` | `#00a36c` / `#ffffff` | The user's chat bubble |
| `positive` | `#00a36c` | Income, gains, on track |
| `negative` | `#e4252d` | Losses, over budget, errors |
| `spend` | `#e4252d` | Spending in income-vs-spending pairs |
| `warn` | `#e59a12` | Needs attention soon |
| `scrim` | `rgb(15 23 42 / 0.4)` | Behind modals |

### Web, dark (night mode)

| Token | Value |
|---|---|
| `bg` / `surface` / `raised` | `#0b1426` / `#111c33` / `#18243f` |
| `line` / `line-strong` | `#1d2a47` / `#26365a` |
| `ink` / `ink-soft` / `ink-faint` | `#f2f5fa` / `#9aa8c4` / `#8391af` |
| `signal` / `on-signal` | `#2dd48a` / `#0b1426` |
| `user` / `on-user` | `#0d7a54` / `#f2f5fa` |
| `positive` / `negative` / `spend` | `#2dd48a` / `#ff4d4f` / `#ff4d4f` |
| `warn` | `#f5a54a` |
| `scrim` | `rgb(4 9 20 / 0.72)` |

### Mobile

| Token | Light | Dark |
|---|---|---|
| `bg` / `surface` / `raised` | `#F3F5F9` / `#FFFFFF` / `#E9EDF3` | `#0B1426` / `#111C33` / `#18243F` |
| `line` / `lineStrong` | `#E2E7EF` / `#D3DAE5` | `#1D2A47` / `#26365A` |
| `ink` / `inkSoft` / `inkFaint` | `#0E1A2B` / `#5A6678` / `#667085` | `#F2F5FA` / `#9AA8C4` / `#8391AF` |
| `accent` / `onAccent` | `#2F6FE0` / `#FFFFFF` | `#2DD48A` / `#0B1426` |
| `userBubble` | `#DCE7FB` | `#0D7A54` |
| `positive` / `negative` | `#15803D` / `#C93A2B` | `#2DD48A` / `#FF4D4F` |
| `spend` | `#7C5CE0` | `#B79CFF` |
| `warn` | `#B45309` | `#F5A54A` |
| `chartLabel` | `rgba(255, 255, 255, 0.88)` | `rgba(4, 9, 20, 0.72)` |

Mobile dark is the web's night mode: the same navy surfaces, ink, green and
red. Only `spend` differs (see *Open differences*).

Bank logos always sit on white (`logoBacking`), because they're drawn for a
light background. Category colors in charts come from `lib/chartColors.ts` in
each app. They're mid-tone fills that read on both themes.

### What color means

- **Green (`positive`)** is money coming in and good news: income, a rising
  net worth, a goal on pace. Income amounts get a `+` and the positive color.
- **Red (`negative`)** is for things that need attention: an error, an
  over-budget goal, a falling net worth, spending ahead of last month's pace.
  A normal credit card balance is not a problem, so on mobile it stays neutral
  with a minus sign. Category increases in chat chart breakdowns are red by
  choice.
- **Ordinary spending** is the most common thing on screen. On mobile it's
  neutral `ink` in lists and `spend` (purple) in charts, so red keeps its
  meaning. The web currently uses red for `spend`; see *Open differences*.
- **Color is never the only signal.** Pair it with a sign (`+`, `−`), an
  arrow (↗ ↘ ▲ ▼), a label, or hatching (`.hatch-warn`, `.hatch-pos` on the
  web). Contrast is at least 4.5:1 for text.

## Type

**Web:** Plus Jakarta Sans for all text, with `ui-rounded` and `system-ui`
as fallbacks. Figures use the same face. `.font-mono` and `.font-tabular` add
fixed-width digits, so amounts line up in columns. Sourced figures in answers
(`.fig`) get a dotted `signal` underline.

**Mobile:** the system font (San Francisco on iOS, Roboto on Android). There
are no font files to load. Figures use tabular digits.

Mobile scale (`type` in `tokens.ts`; the web uses the same sizes where it can):

| Variant | Size / weight | Use |
|---|---|---|
| `display` | 32 / 700 | Rare hero text |
| `brand` | 26 / 700 | "Bankr" in the top bar |
| `title` | 22 / 700 | Screen titles |
| `heading` | 17 / 600 | Card titles |
| `body` / `strong` | 15 / 400, 600 | Running text, chat answers |
| `label` / `tab` | 15 / 500, 600 | Row titles, tab pills |
| `caption` / `meta` | 13 / 400 | Secondary lines |
| `section` / `eyebrow` | 12, 11 / 600, uppercase, 0.8 tracking | Labels over groups: "ASK BANKR", "TODAY", "WHERE IT WENT" |
| `moneyLarge` | 34 / 700, tabular | Headline figures, such as net worth |
| `money` / `moneySmall` | 15 / 600, 13 / 500, tabular | Amounts in rows and summaries |

## Shape and depth

- **Radii:** 8 (`sm`), 14 (`md`), 16 (`lg`, cards), 24 (`xl`), and full
  pills for tabs, chips and the message box.
- **Cards:** surface fill, 1px `line` border, 16px corners, and in light mode
  a barely-there shadow (`--shadow-card`: `0 1px 2px rgb(15 23 42 / 0.05)`).
  Dark mode has no card shadow; the border does the work. On the web, use the
  `.card` class. On mobile, use `Card`, or `ListRow` with `group` for joined
  rows.
- **Menus and modals:** `--shadow-menu` and `--shadow-modal` over `scrim`.
- **Spacing (mobile `space`):** 4, 8, 12, 16, 24, 32. Page gutters are 16 on
  phones and 24 on desktop.
- **Touch targets** are at least 44pt (mobile) or 44px (web).

## Layout

### Web

- **Top bar:** chat history and the **Bankr** wordmark (22px bold) on the left;
  text-only pill tabs in the center (Chat, Transactions, Cash flow, Health,
  Plan, with the open one filled with `signal`; keys 1–4 switch views); the
  period filter, insights bell, theme toggle and profile menu on the right.
- **Money rail:** a 340px column on the right (desktop only) with net worth,
  upcoming bills and goals as cards. On smaller screens it becomes a sheet
  that drops from the top bar.
- **Main column:** the chat is a centered column (`max-w-2xl`) with the
  message box pinned to the bottom. Transactions and Cash flow use the full
  width, up to about 1200px.
- **Chat bubbles:** the user's are right-aligned, filled with `user`, with the
  bottom-right corner squared. Assistant answers are left-aligned cards with
  the top-left corner squared.

### Mobile

- **Top bar:** settings (gear) on the left, **Bankr** in the center, and on
  the right chat history on the Chat tab or sync elsewhere. All icons use the
  accent color.
- **Tabs:** a row of pills under the top bar that scrolls sideways and keeps
  the open tab in view. Swiping the page sideways moves between tabs.
- **Lists:** rows grouped into one bordered card per section, with uppercase
  section headers. Each row has a round initial or logo, a title over a
  secondary line, and the amount on the right.
- **Chat:** an empty chat opens on a net worth card (history line, 1W–1Y
  ranges) and the starter questions as a grouped list. The message box is a
  pill above the home indicator.
- **Sheets:** settings, history, sources and filters open as native form
  sheets.

## Writing

- Plain, friendly sentences. Say what happened and what to do next.
- Section labels are short and uppercase. Buttons are verbs ("Refresh from
  bank", "Link another bank").
- Amounts are exact, with cents in lists and whole dollars in chart labels.
  Never round a figure in a way that changes its meaning.

## Open differences

The two apps drifted while the web palette moved to green. Decide these
together, then update this file:

| | Web | Mobile |
|---|---|---|
| Accent in light mode | Money green (`#00a36c`) | Blue (`#2F6FE0`) |
| Font | Plus Jakarta Sans | System font (San Francisco) |
| Spending color | Red (`spend` = `negative`) | Neutral in lists, purple in charts |
| How dark mode is chosen | Manual toggle; defaults to light | Follows the system, with a System/Light/Dark setting |
