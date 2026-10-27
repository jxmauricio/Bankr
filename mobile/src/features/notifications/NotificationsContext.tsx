import { createContext, use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  fetchInsights,
  fetchLatestRecap,
  markAllInsightsRead,
  markInsightRead,
  markRecapRead,
  type Insight,
  type WeeklyRecap,
} from "@/lib/api";
import { useSession } from "@/lib/session";

/**
 * What the bell, its list and the home screen's recap card share: the
 * notifications (insights, alerts and recaps, newest first) and the latest
 * weekly recap. Reading or dismissing one updates all three at once.
 */
interface Notifications {
  insights: Insight[];
  unreadCount: number;
  /** Null until there's a finished week to recap (or while it loads). */
  latestRecap: WeeklyRecap | null;
  loaded: boolean;
  failed: boolean;
  reload: () => Promise<void>;
  markRead: (insight: Insight) => void;
  markAllRead: () => void;
  /** Opening or dismissing a recap; also clears its row in the list. */
  markRecapRead: (weekStart: string) => void;
}

const NotificationsContext = createContext<Notifications | null>(null);

export function NotificationsProvider({ syncVersion, children }: { syncVersion: number; children: ReactNode }) {
  const { token, signOut } = useSession();
  const [insights, setInsights] = useState<Insight[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [latestRecap, setLatestRecap] = useState<WeeklyRecap | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  // Bumped to load again; the effect below is the only place a load starts.
  const [attempt, setAttempt] = useState(0);
  const onDone = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    // The recap first: asking for it is what makes this week's, and logs its notification.
    fetchLatestRecap(token)
      .then(({ recap }) => fetchInsights(token).then((list) => ({ recap, list })))
      .then(
        ({ recap, list }) => {
          if (cancelled) return;
          setLatestRecap(recap);
          setInsights(list.insights);
          setUnreadCount(list.unread_count);
          setFailed(false);
          setLoaded(true);
        },
        (err: unknown) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) return signOut();
          // A failed refresh keeps what's on screen.
          setFailed(true);
          setLoaded(true);
        }
      )
      .finally(() => {
        onDone.current?.();
        onDone.current = null;
      });
    return () => {
      cancelled = true;
    };
  }, [token, signOut, syncVersion, attempt]);

  /** Loads again; resolves when done (pull to refresh). */
  const reload = useCallback(
    () =>
      new Promise<void>((resolve) => {
        onDone.current = resolve;
        setAttempt((n) => n + 1);
      }),
    []
  );

  const clearLocally = useCallback((isIt: (i: Insight) => boolean) => {
    setInsights((list) => {
      const newlyRead = list.filter((i) => !i.read && isIt(i)).length;
      if (newlyRead) setUnreadCount((n) => Math.max(0, n - newlyRead));
      return list.map((i) => (isIt(i) ? { ...i, read: true } : i));
    });
  }, []);

  const markRead = useCallback(
    (insight: Insight) => {
      if (!token || insight.read) return;
      clearLocally((i) => i.id === insight.id);
      if (insight.type === "weekly_recap") setLatestRecap((r) => (r && r.week_start === insight.subject_id ? { ...r, read: true } : r));
      markInsightRead(token, insight.id).catch(() => {});
    },
    [token, clearLocally]
  );

  const markAllRead = useCallback(() => {
    if (!token) return;
    clearLocally(() => true);
    setLatestRecap((r) => (r ? { ...r, read: true } : r));
    markAllInsightsRead(token).catch(() => {});
  }, [token, clearLocally]);

  const recapRead = useCallback(
    (weekStart: string) => {
      if (!token) return;
      clearLocally((i) => i.type === "weekly_recap" && i.subject_id === weekStart);
      setLatestRecap((r) => (r && r.week_start === weekStart ? { ...r, read: true } : r));
      markRecapRead(token, weekStart).catch(() => {});
    },
    [token, clearLocally]
  );

  return (
    <NotificationsContext
      value={{ insights, unreadCount, latestRecap, loaded, failed, reload, markRead, markAllRead, markRecapRead: recapRead }}
    >
      {children}
    </NotificationsContext>
  );
}

export function useNotifications(): Notifications {
  const ctx = use(NotificationsContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationsProvider");
  return ctx;
}
