import * as Sentry from "@sentry/react";
import { scrubReport, stripQuery } from "./scrub";

/**
 * Error reporting. Off unless VITE_SENTRY_DSN is set, so local dev sends
 * nothing. When on, it reports stack traces only. Sentry v11 collects user
 * info, headers, query strings and request bodies by default, so every one of
 * those is denied explicitly below. No session replay, no tracing, no console
 * or click breadcrumbs (they can carry what the user typed or the app logged),
 * and scrubReport strips query strings from any URL that still gets through.
 */
export function initMonitoring() {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0,
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
    },
    integrations: (defaults) => [
      ...defaults.filter((integration) => integration.name !== "Breadcrumbs" && integration.name !== "Console"),
      Sentry.breadcrumbsIntegration({ dom: false, fetch: true, xhr: true, history: true }),
    ],
    beforeSend: scrubReport,
    beforeBreadcrumb(crumb) {
      if (crumb.data) {
        for (const key of ["url", "from", "to"]) {
          if (typeof crumb.data[key] === "string") crumb.data[key] = stripQuery(crumb.data[key]);
        }
      }
      return crumb;
    },
  });
}
