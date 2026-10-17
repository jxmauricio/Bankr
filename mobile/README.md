# Bankr mobile

React Native app (Expo SDK 57, Expo Router) for iOS and Android. Like `web/`,
it holds no secrets and only talks to the backend.

## Run it

```bash
cd mobile
npm install
npx expo start          # then press i for the iOS simulator
```

Until the app needs native modules that Expo Go lacks (Plaid Link will), it
runs in **Expo Go** for SDK 57. A development build (`npx expo run:ios`)
needs **Xcode 26.4+**.

The API defaults to `http://localhost:8000`, which the iOS simulator reaches
directly. On a physical phone, set `EXPO_PUBLIC_API_BASE_URL` to your Mac's
LAN address or a tunnel URL (in `mobile/.env.local`, then restart Metro).

Before calling a change done: `npx tsc --noEmit` and `npx expo lint`.

## Styling is deliberately isolated

The visual design is still being worked out, so nothing outside two folders
knows what the app looks like:

- `src/theme/tokens.ts` — every color, spacing step, radius, font and text
  style. Values follow the "Bankr Mobile" design in Claude Design
  (https://claude.ai/artifact/PLuTHqLnEE4qZ9W8Mhodxt): Space Grotesk for
  words, JetBrains Mono for every figure, loaded in `src/app/_layout.tsx`.
- `src/ui/` — the primitives screens are built from (`Screen`, `Text`,
  `Button`, `IconButton`, `Chip`, `Icon`, `TextField`, `Card`, `ListRow`,
  `SegmentedControl`, loading/error states).

Screens use `Text` variants and tones (`variant="money" tone="negative"`), not
raw styles, so a redesign is mostly a change to those two folders. If a screen
needs a look the primitives can't give it, add a variant or a primitive rather
than styling it inline.

## Layout

- `src/app/` — routes (Expo Router). `_layout.tsx` switches between
  `sign-in` and the signed-in `(app)` group. `(app)/_layout.tsx` is the same
  onboarding gate as the web app (no bank, then no goal, then the tabs);
  `(app)/(tabs)/` holds the five native tabs, and `money` and `history` are
  sheets.
- `src/features/` — screen-level pieces: the shared header and money context,
  and `useChat` (streaming, stop, retry, reopening past conversations).
- `src/lib/api.ts` — ported from `web/src/lib/api.ts`. The only differences
  are the base URL and chat streaming through `expo/fetch`. Keep the two in
  step until they move into a shared package.
- `src/lib/session.tsx` — the session token, kept in SecureStore
  (Keychain/Keystore), not plain storage.

## Not built yet

Linking a bank (Plaid Link SDK plus OAuth redirect), standalone goal setup,
the Health and Plan tabs, transaction editing, and voice mode. A new account
is told to link a bank and set a goal on the web for now.
