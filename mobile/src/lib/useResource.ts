import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import { useSession } from "./session";

type State<T> =
  | { status: "loading"; data: T | null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "error"; data: T | null; error: string };

/**
 * Loads one backend resource for the signed-in user. `deps` re-run the load
 * (e.g. a changed period); `reload` does it on demand (pull to refresh). A
 * 401 means the token is dead, so it signs out rather than showing an error.
 */
export function useResource<T>(load: (token: string) => Promise<T>, deps: unknown[] = []) {
  const { token, signOut } = useSession();
  const [state, setState] = useState<State<T>>({ status: "loading", data: null, error: null });
  const [refreshing, setRefreshing] = useState(false);
  // Bumped to load again; the effect below is the only place a load starts.
  const [attempt, setAttempt] = useState(0);
  const onDone = useRef<(() => void) | null>(null);
  const loadRef = useRef(load);
  // Declared before the load effect, so a re-run sees the latest `load`.
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    loadRef
      .current(token)
      .then(
        (data) => {
          if (!cancelled) setState({ status: "ready", data, error: null });
        },
        (err: unknown) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) return signOut();
          const message = err instanceof Error ? err.message : "Something went wrong.";
          setState((s) => ({ status: "error", data: s.data, error: message }));
        }
      )
      .finally(() => {
        onDone.current?.();
        onDone.current = null;
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, signOut, attempt, ...deps]);

  const retry = useCallback(() => {
    setState((s) => ({ status: "loading", data: s.data, error: null }));
    setAttempt((n) => n + 1);
  }, []);

  const reload = useCallback(() => {
    setRefreshing(true);
    onDone.current = () => setRefreshing(false);
    setAttempt((n) => n + 1);
  }, []);

  return { ...state, refreshing, reload, retry };
}
