# Bankr mobile

React Native app (Expo SDK 57, Expo Router) for iOS and Android. Like `web/`,
it holds no secrets and only talks to the backend.

## Run it

```bash
cd mobile
npm install
npx expo run:ios        # first time, or after adding native code: builds the dev client
npx expo start          # every other time; open the installed Bankr app
```

The app runs as its own development build (`expo-dev-client`), not in Expo
Go, so native modules like Plaid Link work. Building it locally needs
**Xcode 26.4+** (which needs macOS Tahoe 26.2+); without that, build in the
cloud with EAS. A rebuild is only needed when native code or `app.json`
changes; everything in `src/` reloads live.

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

## Linking a bank

Plaid Link runs natively (`react-native-plaid-link-sdk`, in
`src/features/bank/useLinkBank.ts`): new users link from onboarding, others
from the money sheet's "Link another bank". The app asks the backend for a
link token with `?platform=ios|android`, so it never gets the web app's
OAuth redirect.

OAuth banks (Chase, Capital One, ...) also need, once:
- **iOS:** an HTTPS universal link for the app (an apple-app-site-association
  file on a domain you control, plus associated domains in `app.json`), set as
  `PLAID_IOS_REDIRECT_URI` on the backend and registered in the Plaid Dashboard.
- **Android:** the package name (`com.bankr.app`) registered in the Plaid
  Dashboard and set as `PLAID_ANDROID_PACKAGE_NAME`.

Until then those banks may not link from the app; non-OAuth banks do.

## Not built yet

Standalone goal setup, the Health and Plan tabs, transaction editing, voice
mode, and the OAuth universal link above. A new account sets its first goal
on the web for now.
