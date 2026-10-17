import * as SecureStore from "expo-secure-store";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

// The backend session JWT lives in the Keychain (iOS) / Keystore (Android),
// not plain storage. Same key as the web app's localStorage entry.
const STORAGE_KEY = "bankr_session_token";

interface SessionContextValue {
  token: string | null;
  isAuthenticated: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  // Read synchronously once at launch so the first frame already knows
  // whether to show sign-in, instead of flashing it while a promise resolves.
  const [token, setToken] = useState<string | null>(() => SecureStore.getItem(STORAGE_KEY));

  const signIn = useCallback((newToken: string) => {
    setToken(newToken);
    SecureStore.setItemAsync(STORAGE_KEY, newToken).catch(() => {
      // Still signed in for this launch; they'll just sign in again next time.
    });
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    SecureStore.deleteItemAsync(STORAGE_KEY).catch(() => {});
  }, []);

  const value = useMemo(
    () => ({ token, isAuthenticated: token !== null, signIn, signOut }),
    [token, signIn, signOut]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within a SessionProvider");
  return ctx;
}

/** For screens behind the auth guard, where a token is always present. */
export function useToken(): string {
  const { token } = useSession();
  if (!token) throw new Error("useToken used outside the signed-in routes");
  return token;
}
