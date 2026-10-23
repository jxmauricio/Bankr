import { useCallback, useState } from "react";
import { Platform } from "react-native";
import { createPlaidLinkSession } from "react-native-plaid-link-sdk";
import { ApiError, fetchLinkToken, linkAccount, type LinkAccountResponse } from "@/lib/api";
import { useSession } from "@/lib/session";

/**
 * Plaid Link, native: get a link token for this platform, open Plaid's bank
 * login, then hand the public token to the backend, which exchanges it and
 * syncs. Same backend calls as the web LinkBankPage. Closing Plaid without
 * linking is not an error.
 */
export function useLinkBank(onLinked: (result: LinkAccountResponse) => void | Promise<void>) {
  const { token, signOut } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback(
    (err: unknown, fallback: string) => {
      if (err instanceof ApiError && err.status === 401) return signOut();
      setError(err instanceof ApiError ? err.message : fallback);
      setBusy(false);
    },
    [signOut]
  );

  const link = useCallback(async () => {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { link_token } = await fetchLinkToken(token, Platform.OS === "android" ? "android" : "ios");
      const session = await createPlaidLinkSession({
        token: link_token,
        onSuccess: async (success) => {
          try {
            const result = await linkAccount(token, success.publicToken);
            await onLinked(result);
            setBusy(false);
          } catch (err) {
            fail(err, "Your bank connected, but Bankr couldn't load it. Try again.");
          }
        },
        onExit: (exit) => {
          // Closing Plaid on purpose still sends an error object, just an empty
          // one; only a described error is worth showing.
          const message = exit.error?.displayMessage || exit.error?.errorMessage;
          if (message) setError(message);
          setBusy(false);
        },
        onEvent: () => {},
      });
      await session.open();
    } catch (err) {
      fail(err, "Couldn't start bank linking. Check your connection and try again.");
    }
  }, [token, busy, onLinked, fail]);

  return { link, busy, error };
}
